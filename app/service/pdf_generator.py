#! /usr/bin/env python3
## File: pdf_generator.py

"""
PDF generation service for creating reports
Handles PDF creation from DataFrame data with proper formatting.
"""
import asyncio
from typing import List, Tuple, Optional
import pandas as pd
from datetime import datetime, timedelta

from app.utils.log_settings import setup_logging
from app.database.connection import SupabaseHandler
from app.service.chart_generator import ChartGenerator

logger = setup_logging('pdf_generator.log')

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
    PDFType = FPDF
except ImportError:
    FPDF = None
    FPDF_AVAILABLE = False
    PDFType = object  # Fallback type for type hints
    logger.warning("FPDF library not available - PDF generation disabled")

class PDFGenerator:
    """Service for generating PDF reports from DataFrame data"""

    def __init__(self):
        self.font = "Arial"
        self.max_col_width = 40  # mm
        self.max_cell_chars = 20
        self.page_margin = 15
        self.header_height = 10
        self.row_height = 8
        self.total_volume = SupabaseHandler()
        self.chart_generator = ChartGenerator()
        self._cached_total_volume = None  # Cache for sync methods
        self._cached_product_counts = None  # Cache product counts fetched from DB
        self._cached_product_chart_bytes = None  # Cache product pie chart bytes
    
    async def generate(self, data_frames: dict[str, pd.DataFrame], title: str, 
                      footnote: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
        """Generate PDF asynchronously from dictionary of DataFrames"""
        if not FPDF_AVAILABLE:
            return None, "FPDF library not installed - cannot generate PDF"
        
        if not data_frames:
            return None, "No data provided for PDF generation"
        
        # Concatenate all DataFrames for summary and chart generation
        all_data_df = pd.concat(data_frames.values(), ignore_index=True)
        if all_data_df.empty:
            return None, "No data provided for PDF generation after concatenation"
        
        try:
            # Pre-cache the total volume for sync methods
            try:
                self._cached_total_volume = await self.total_volume.get_total_volume_loaded()
                logger.debug(f"Cached total volume: {self._cached_total_volume}")
            except Exception as e:
                logger.warning(f"Could not cache total volume: {e}")
                self._cached_total_volume = None

            # Pre-fetch product counts from database tables and generate product pie chart bytes in thread
            try:
                self._cached_product_counts = await self.total_volume.get_product_counts()
                logger.debug(f"Cached product counts: {self._cached_product_counts}")
            except Exception as e:
                logger.warning(f"Could not fetch product counts: {e}")
                self._cached_product_counts = None

            if self._cached_product_counts:
                # Generate pie chart bytes using matplotlib in a thread to avoid blocking
                try:
                    self._cached_product_chart_bytes = await asyncio.to_thread(
                        self.chart_generator.generate_product_pie_chart_from_counts,
                        self._cached_product_counts
                    )
                    logger.debug("Cached product pie chart bytes")
                except Exception as e:
                    logger.warning(f"Could not generate product pie chart: {e}")
                    self._cached_product_chart_bytes = None
            else:
                self._cached_product_chart_bytes = None
            
            # Run PDF generation in thread pool to avoid blocking
            pdf_data = await asyncio.to_thread(self._generate_pdf_sync, data_frames, all_data_df, title, footnote)
            logger.info(f"Successfully generated PDF with {len(all_data_df)} records")
            return pdf_data, None
        
        except Exception as e:
            error_msg = f"PDF generation failed: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def _generate_pdf_sync(self, data_frames: dict[str, pd.DataFrame], all_data_df: pd.DataFrame, title: str,
                           footnote: Optional[str] = None) -> bytes:
        """Synchronous PDF generation"""
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=self.page_margin)
        pdf.add_page()

        # Add summary statistics at the top
        self._add_summary_statistics_section(pdf, all_data_df)

        

        # Add table headers
        #self._add_table_headers(pdf, all_data_df.columns)

        # Add data rows
        self._add_data_rows_from_dict(pdf, data_frames)

        # Add charts at the bottom
        self._add_charts_section(pdf, all_data_df)

        # Add footnote if provided
        if footnote:
            self._add_footnote(pdf, footnote)
        
        # Return PDF as bytes
        return self._write_pdf_data(pdf)
    
    def _write_pdf_data(self, pdf: PDFType) -> bytes:
        """Write PDF data to bytes"""
        pdf_output = pdf.output(dest='S')
        if isinstance(pdf_output, str):
            return pdf_output.encode('utf-8', errors='replace')
        return pdf_output
    
    def _add_title(self, pdf, title: str) -> None:
        """Add title section to PDF"""
        pdf.set_font(self.font, 'B', 16)
        pdf.cell(0, self.header_height, title, ln=True, align='C')
        pdf.ln(self.header_height)
    
    def _add_table_headers(self, pdf, columns: pd.Index) -> None:
        """Add table headers with proper formatting"""
        col_widths = self._calculate_column_widths(pdf, columns)
        pdf.set_font(self.font, 'B', 8)

        # Set header background color 
        pdf.set_fill_color(220, 220, 220)  # light gray

        for col, width in zip(columns, col_widths):
            col_text = self._truncate_text(str(col), 15)
            pdf.cell(width, self.row_height, col_text, border=0, align='C', fill=True)
        
        pdf.ln()
    
    
    
    def _add_summary_statistics_section(self, pdf, df: pd.DataFrame) -> None:
        """Add summary statistics to the PDF"""
        # Generate summary statistics using cached volume
        summary_data = self._generate_summary_stats_cached(df)
        
        # Add some space before summary
        pdf.ln(10)
        
        # Add separator line
        pdf.set_draw_color(128, 128, 128)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(5)
        
        # Add summary title
        pdf.set_font(self.font, 'B', 12)
        pdf.set_text_color(0, 0, 0)  # Reset to black
        pdf.cell(0, 8, "Summary Statistics", ln=True, align='C')
        pdf.ln(3)
        
        # Add summary data in two columns
        pdf.set_font(self.font, size=10)
        
        # Calculate column width for two-column layout
        col_width = (pdf.w - 2 * pdf.l_margin) / 2
        
        items = list(summary_data.items())
        for i in range(0, len(items), 2):
            # Left column
            key1, value1 = items[i]
            display_key1 = key1.replace('_', ' ').title()
            pdf.cell(col_width, 6, f"{display_key1}: {value1}", border=0)
            
            # Right column (if exists)
            if i + 1 < len(items):
                key2, value2 = items[i + 1]
                display_key2 = key2.replace('_', ' ').title()
                pdf.cell(col_width, 6, f"{display_key2}: {value2}", border=0)
            
            pdf.ln()

    def _add_charts_section(self, pdf, df: pd.DataFrame) -> None:
        """Add charts to the PDF"""
        # Generate BDC volume chart
        chart_bytes = None
        if self.chart_generator.is_available():
            try:
                chart_bytes = self.chart_generator.generate_bdc_volume_chart(df, self._cached_total_volume)
            except Exception as e:
                logger.warning(f"Could not generate BDC chart: {e}")
        
        # Add BDC chart if available
        if chart_bytes:
            try:
                self._add_chart_to_pdf(pdf, chart_bytes, "BDC Volume Distribution")
            except Exception as e:
                logger.warning(f"Could not add chart to PDF: {e}")

        # Add product distribution pie chart (from cached product chart bytes) if available
        if getattr(self, '_cached_product_chart_bytes', None):
            try:
                self._add_chart_to_pdf(pdf, self._cached_product_chart_bytes, "Product Loaded Distribution (PMS / AGO / Others)")
            except Exception as e:
                logger.warning(f"Could not add product distribution chart to PDF: {e}")

    def _add_data_rows_from_dict(self, pdf, data_frames: dict[str, pd.DataFrame]) -> None:
        """Add data rows from a dictionary of DataFrames, using keys as status"""
        main_columns = [
            'order_date', 'order_number', 'products', 'volume',
            'ex_ref_price', 'brv_number', 'bdc'
        ]

        pdf.set_font(self.font, size=7)

        for status, df_group in data_frames.items():
            if df_group.empty:
                continue

            # Add status as a new section title
            pdf.ln(5) # Add some space
            pdf.set_font(self.font, 'B', 10)
            pdf.cell(0, self.row_height,  status, ln=True, align='L')
            pdf.ln(2)

            # Ensure only main columns are used and preserve original order
            df_display = df_group[[col for col in main_columns if col in df_group.columns]]

            # Add table headers for this group
            col_widths = self._calculate_column_widths(pdf, df_display.columns)
            pdf.set_font(self.font, 'B', 8)
            pdf.set_fill_color(220, 220, 220)  # light gray
            for col, width in zip(df_display.columns, col_widths):
                col_text = self._truncate_text(str(col), 15)
                pdf.cell(width, self.row_height, col_text, border=0, align='C', fill=True)
            pdf.ln()

            # Add data rows for the current status group
            row_count = 0
            for _, row in df_display.iterrows():
                # Check if we need a new page (leave space for summary)
                if pdf.get_y() + self.row_height + 50 > pdf.h - self.page_margin:  # 50mm for summary space
                    pdf.add_page()
                    # Re-add status title and headers on new page
                    pdf.ln(5)
                    pdf.set_font(self.font, 'B', 10)
                    pdf.cell(0, self.row_height,  status, ln=True, align='L')
                    pdf.ln(2)
                    pdf.set_font(self.font, 'B', 8)
                    pdf.set_fill_color(220, 220, 220)  # light gray
                    for col, width in zip(df_display.columns, col_widths):
                        col_text = self._truncate_text(str(col), 15)
                        pdf.cell(width, self.row_height, col_text, border=0, align='C', fill=True)
                    pdf.ln()

                # Add alternating row colors for better readability
                fill = row_count % 2 == 0
                if fill:
                    pdf.set_fill_color(245, 245, 245)
                else:
                    pdf.set_fill_color(255, 255, 255)
                
                # Add each cell in the row
                pdf.set_font(self.font, size=7)
                for col, width in zip(df_display.columns, col_widths):
                    cell_value = row[col]
                    cell_text = self._format_cell_value(cell_value)
                    pdf.cell(width, self.row_height, cell_text, border=0, fill=fill)
                
                pdf.ln()
                row_count += 1

    def _add_footnote(self, pdf, footnote: str) -> None:
        """Add footnote at the bottom of the PDF"""
        # Move to bottom of page
        pdf.set_y(-25)

        # Add line separator
        pdf.set_draw_color(128, 128, 128)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(5)

        # Add footnote text
        pdf.set_font(self.font, 'I', 9)
        pdf.set_text_color(100, 100, 100)
        pdf.multi_cell(0, 4, footnote, align='C')
    
    def _calculate_column_widths(self, pdf, columns: pd.Index) -> List[float]:
        """Calculate optimal column widths based on content"""
        page_width = pdf.w - (2 * pdf.l_margin)
        num_cols = len(columns)

        # Base width distribution
        base_width = min(page_width / num_cols, self.max_col_width)
        
        # Adjust widths based on column names and content
        widths = []
        for col in columns:
            col_name = str(col)

            # Wider columns for longer names 
            if len(col_name) > 15 or col_name == 'BDC':
                width = min(base_width * 1.5, self.max_col_width)
            elif col_name in ['ORDER_DATE', 'ORDER_NUMBER', 'BRV_NUMBER', 'PRODUCTS']:
                width = base_width * 1.2
            else:
                width = base_width

            widths.append(width)

        # Normalize widths to fit page
        total_width = sum(widths)
        if total_width > page_width:
            scale_factor = page_width / total_width
            widths = [w * scale_factor for w in widths]
        
        return widths
        
    def _format_cell_value(self, value) -> str:
        """Format cell value for display in PDF"""
        if pd.isna(value):
            return ""
        
        # Handle different data types
        if isinstance(value, pd.Timestamp):
            return value.strftime('%d-%m-%Y')
        elif isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            else:
                return f"{value:.2f}"
        else:
            return self._truncate_text(str(value), self.max_cell_chars)
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length with ellipsis"""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."

    async def generate_summary_report(self, df: pd.DataFrame, title: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Generate a summary report with statistics"""
        if not FPDF_AVAILABLE:
            return None, "FPDF library not available"
        try:
            # Pre-cache the total volume for consistency
            try:
                self._cached_total_volume = await self.total_volume.get_total_volume_loaded()
            except Exception as e:
                logger.warning(f"Could not cache total volume: {e}")
                self._cached_total_volume = None
                
            summary_data = await self._generate_summary_stats(df)

            # Create summary PDF
            pdf_data = await asyncio.to_thread(self._generate_summary_pdf, summary_data, title)
            return pdf_data, None
        
        except Exception as e:
            error_msg = f"Summary report generation failed: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    async def _generate_summary_stats(self, df: pd.DataFrame) -> dict:
        """Generate summary statistics from DataFrame"""
        main_columns = [
            'order_date', 'order_number', 'products', 'volume',
            'ex_ref_price', 'brv_number', 'bdc'
        ]
        df = df[[col for col in main_columns if col in df.columns]]

        stats = {
            'total_records': len(df),
            'date_range': 'N/A',
            'active_bdcs': 'N/A',
            'total_volume_loaded': 'N/A'
        }

        try:
            # Date range
            if 'ORDER_DATE' in df.columns:
                dates = pd.to_datetime(df['ORDER_DATE'], errors='coerce').dropna()
                if not dates.empty:
                    min_date = dates.min().strftime('%d-%m-%Y')
                    max_date = dates.max().strftime('%d-%m-%Y')
                    if min_date == max_date:
                        stats['date_range'] = max_date
                    else:
                        stats['date_range'] = f"{min_date} to {max_date}"
            
            # Volume sum
            try:
                total_volume = await self.total_volume.get_total_volume_loaded()
                stats['total_volume_loaded'] = f"{total_volume:,.0f}"
            except Exception as e:
                logger.warning(f"Could not get total volume: {e}")
                stats['total_volume_loaded'] = "N/A"
            
            # BDC count
            if 'BDC' in df.columns:
                stats['active_bdcs'] = df['BDC'].nunique()

        except Exception as e:
            logger.warning(f"Error generating summary stats: {e}")
        
        return stats
    
    def _generate_summary_stats_cached(self, df: pd.DataFrame) -> dict:
        """Generate summary statistics using cached volume data (synchronous)"""
        main_columns = [
            'order_date', 'order_number', 'products', 'volume',
            'ex_ref_price', 'brv_number', 'bdc'
        ]
        df = df[[col for col in main_columns if col in df.columns]]

        today = datetime.now()
        yesterday = today - timedelta(days=1)

        stats = {
            'total_records': len(df),
            'depot': 'BOST-KUMASI',
            'date_range': f"{yesterday.strftime('%d-%m-%Y')} to {today.strftime('%d-%m-%Y')}",
            'total_volume_loaded': 'N/A'
        }

        try:
            
            # Volume sum - Use cached database volume for consistency
            if self._cached_total_volume is not None:
                stats['total_volume_loaded'] = f"{self._cached_total_volume:,.0f}"
                logger.debug(f"Using cached volume: {self._cached_total_volume}")
            else:
                stats['total_volume_loaded'] = "N/A"
                logger.warning("No cached volume available")
        
        except Exception as e:
            logger.warning(f"Error generating summary stats: {e}")
        
        return stats
    
    def _generate_summary_pdf(self, summary_data: dict, title: str) -> bytes:
        """Generate summary PDF with statistics"""
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=self.page_margin)
        pdf.add_page()
        
        # Title
        self._add_title(pdf, f"{title} - Summary Report")
        
        # Summary statistics
        pdf.set_font(self.font, 'B', 12)
        pdf.cell(0, 10, "Summary Statistics", ln=True)
        pdf.ln(5)
        
        pdf.set_font(self.font, size=10)
        for key, value in summary_data.items():
            display_key = key.replace('_', ' ').title()
            pdf.cell(0, 8, f"{display_key}: {value}", ln=True)
        
        pdf_output = pdf.output(dest='S')
        return pdf_output.encode('utf-8', errors='replace') if isinstance(pdf_output, str) else pdf_output
    
    def _add_chart_to_pdf(self, pdf, chart_bytes: bytes, chart_title: str) -> None:
        """Add chart image to PDF"""
        try:
            import tempfile
            import os
            
            # Check if we need a new page for the chart
            available_height = pdf.h - pdf.get_y() - pdf.b_margin
            chart_height = 80  # Estimated chart height in mm
            
            if available_height < chart_height + 20:  # Add some buffer
                pdf.add_page()
            
            # Add some space before chart
            pdf.ln(10)
            
            # Add chart title
            pdf.set_font(self.font, 'B', 11)
            pdf.cell(0, 8, chart_title, ln=True, align='C')
            pdf.ln(5)
            
            # Save chart to temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_file.write(chart_bytes)
                tmp_file_path = tmp_file.name
            
            try:
                # Calculate chart dimensions to fit page width
                page_width = pdf.w - 2 * pdf.l_margin
                chart_width = min(page_width * 0.9, 150)  # Max 150mm width
                
                # Center the chart horizontally
                x_offset = (pdf.w - chart_width) / 2
                
                # Add image to PDF
                pdf.image(tmp_file_path, x=x_offset, y=pdf.get_y(), w=chart_width)
                
                # Move cursor below the image
                pdf.ln(chart_height)
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error adding chart to PDF: {e}")
            # Add text fallback if chart fails
            pdf.set_font(self.font, 'I', 9)
            pdf.cell(0, 6, f"[Chart: {chart_title} - Generation failed]", ln=True, align='C')