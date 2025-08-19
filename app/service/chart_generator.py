#! /usr/bin/env python3
## File: chart_generator.py

"""
Chart generation service for creating visualizations
Handles chart creation from DataFrame data for PDF reports.
"""
import io
from typing import Optional, Dict, List, Tuple
import pandas as pd

# Configure matplotlib for non-interactive use first
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to prevent GUI issues
from app.utils.log_settings import setup_logging

logger = setup_logging('chart_generator.log')

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    plt = None
    MATPLOTLIB_AVAILABLE = False
    logger.warning("Matplotlib not available - chart generation disabled")

class ChartGenerator:
    """Service for generating charts from DataFrame data"""

    def __init__(self):
        self.figure_size = (10, 6)
        self.dpi = 100
        self.bar_color = '#2E86AB'
        self.text_color = '#333333'
        self.grid_color = '#E0E0E0'
        
    def generate_bdc_volume_chart(self, df: pd.DataFrame, total_volume_loaded: Optional[float] = None) -> Optional[bytes]:
        """Generate bar chart showing BDC volume distribution"""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available - cannot generate chart")
            return None
            
        if df is None or df.empty:
            logger.warning("No data provided for chart generation")
            return None
            
        try:
            # Extract and aggregate BDC volume data
            bdc_data = self._extract_bdc_volume_data(df, total_volume_loaded)
            
            if not bdc_data:
                logger.warning("No BDC volume data found")
                return None
                
            # Create the chart
            chart_bytes = self._create_bar_chart(bdc_data)
            logger.info(f"Successfully generated BDC volume chart with {len(bdc_data)} BDCs")
            return chart_bytes
            
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            return None
    
    def _extract_bdc_volume_data(self, df: pd.DataFrame, total_volume_loaded: Optional[float] = None) -> List[Dict]:
        """Extract and aggregate BDC volume data from DataFrame"""
        bdc_data = []
        
        try:
            # Check for BDC column (case insensitive)
            bdc_column = None
            volume_column = None
            
            for col in df.columns:
                if col.upper() == 'BDC':
                    bdc_column = col
                elif col.upper() in ['VOLUME', 'VOL']:
                    volume_column = col
            
            if bdc_column is None:
                logger.warning("No BDC column found in DataFrame")
                return []
            
            # Group by BDC and sum volumes
            if bdc_column and volume_column in df.columns:
                # Use actual volume data from DataFrame
                bdc_volumes = df.groupby(bdc_column)[volume_column].sum().sort_values(ascending=False)
                
                for bdc, volume in bdc_volumes.items():
                    if pd.notna(bdc) and pd.notna(volume) and volume > 0:
                        bdc_data.append({
                            'bdc': str(bdc),
                            'volume': float(volume),
                            'percentage': 0.0  # Will calculate later
                        })
            else:
                # Use record count as proxy for volume distribution
                bdc_counts = df[bdc_column].value_counts()
                
                # If we have total_volume_loaded, distribute it proportionally
                if total_volume_loaded and total_volume_loaded > 0:
                    total_records = len(df)
                    for bdc, count in bdc_counts.items():
                        if pd.notna(bdc) and count > 0:
                            # Distribute total volume proportionally by record count
                            estimated_volume = (count / total_records) * total_volume_loaded
                            bdc_data.append({
                                'bdc': str(bdc),
                                'volume': float(estimated_volume),
                                'percentage': 0.0  # Will calculate later
                            })
                else:
                    # Just use record counts
                    for bdc, count in bdc_counts.items():
                        if pd.notna(bdc) and count > 0:
                            bdc_data.append({
                                'bdc': str(bdc),
                                'volume': float(count),  # Using count as volume proxy
                                'percentage': 0.0
                            })
            
            # Calculate percentages
            if bdc_data:
                total_volume = sum(item['volume'] for item in bdc_data)
                for item in bdc_data:
                    item['percentage'] = (item['volume'] / total_volume) * 100 if total_volume > 0 else 0
                
                # Sort by volume descending
                bdc_data.sort(key=lambda x: x['volume'], reverse=True)
                
                # Limit to top 15 BDCs for readability
                if len(bdc_data) > 15:
                    other_volume = sum(item['volume'] for item in bdc_data[15:])
                    other_percentage = sum(item['percentage'] for item in bdc_data[15:])
                    bdc_data = bdc_data[:15]
                    if other_volume > 0:
                        bdc_data.append({
                            'bdc': 'Others',
                            'volume': other_volume,
                            'percentage': other_percentage
                        })
            
            logger.info(f"Extracted {len(bdc_data)} BDC volume entries")
            return bdc_data
            
        except Exception as e:
            logger.error(f"Error extracting BDC volume data: {e}")
            return []
    
    def _create_bar_chart(self, bdc_data: List[Dict]) -> bytes:
        """Create bar chart from BDC volume data"""
        # Set up the figure and axis
        plt.style.use('default')
        fig, ax = plt.subplots(figsize=self.figure_size, dpi=self.dpi)
        
        # Extract data for plotting
        bdcs = [item['bdc'] for item in bdc_data]
        volumes = [item['volume'] for item in bdc_data]
        percentages = [item['percentage'] for item in bdc_data]
        
        # Create bar chart
        bars = ax.bar(range(len(bdcs)), volumes, color=self.bar_color, alpha=0.8, edgecolor='white', linewidth=0.5)
        
        # Customize the chart
        ax.set_xlabel('BDC', fontsize=12, color=self.text_color, fontweight='bold')
        ax.set_ylabel('Volume', fontsize=12, color=self.text_color, fontweight='bold')
        ax.set_title('Volume Distribution by BDC (All orders)', fontsize=14, color=self.text_color, fontweight='bold', pad=20)
        
        # Set x-axis labels
        ax.set_xticks(range(len(bdcs)))
        ax.set_xticklabels(bdcs, rotation=45, ha='right', fontsize=10)
        
        # Format y-axis
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        
        # Add value labels on top of bars
        for i, (bar, volume, percentage) in enumerate(zip(bars, volumes, percentages)):
            height = bar.get_height()
            # Show volume and percentage
            if volume >= 1000:
                volume_text = f'{volume:,.0f}'
            else:
                volume_text = f'{volume:.1f}'
            
            ax.text(bar.get_x() + bar.get_width()/2., height + max(volumes) * 0.01,
                   f'{volume_text}\n({percentage:.1f}%)',
                   ha='center', va='bottom', fontsize=8, color=self.text_color)
        
        # Add grid for better readability
        ax.grid(True, alpha=0.3, color=self.grid_color, linestyle='-', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Adjust layout to prevent label cutoff
        plt.tight_layout()
        
        # Adjust y-axis to accommodate labels
        y_max = max(volumes)
        ax.set_ylim(0, y_max * 1.15)
        
        # Save to bytes
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='PNG', dpi=self.dpi, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        img_buffer.seek(0)
        chart_bytes = img_buffer.getvalue()
        
        # Clean up
        plt.close(fig)
        img_buffer.close()
        
        return chart_bytes
    
    def generate_summary_charts(self, df: pd.DataFrame, total_volume_loaded: Optional[float] = None) -> Dict[str, Optional[bytes]]:
        """Generate multiple charts for summary report"""
        charts = {}
        
        try:
            # BDC Volume Distribution Chart
            charts['bdc_volume'] = self.generate_bdc_volume_chart(df, total_volume_loaded)
            
            # Could add more chart types here in the future:
            # charts['daily_trend'] = self.generate_daily_trend_chart(df)
            # charts['product_distribution'] = self.generate_product_chart(df)
            
            logger.info(f"Generated {len([c for c in charts.values() if c is not None])} charts")
            
        except Exception as e:
            logger.error(f"Error generating summary charts: {e}")
        
        return charts
    
    @staticmethod
    def is_available() -> bool:
        """Check if chart generation is available"""
        return MATPLOTLIB_AVAILABLE
    
    def generate_product_pie_chart_from_counts(self, product_counts: Dict[str, int]) -> Optional[bytes]:
        """Generate a pie chart showing product distribution (PMS, AGO, Others) from counts dict.

        product_counts: mapping of product name -> count
        Returns PNG bytes or None on failure.
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available - cannot generate product pie chart")
            return None

        try:
            # Normalize keys (uppercase) and aggregate
            counts = {}
            for k, v in (product_counts or {}).items():
                key = (k or 'Unknown').strip().upper()
                counts[key] = counts.get(key, 0) + int(v)

            # Focus on PMS and AGO; everything else to 'Others'
            pms = counts.get('PMS', 0)
            ago = counts.get('AGO', 0)
            other_total = sum(v for k, v in counts.items() if k not in ('PMS', 'AGO'))

            labels = []
            sizes = []
            if pms > 0:
                labels.append('PMS')
                sizes.append(pms)
            if ago > 0:
                labels.append('AGO')
                sizes.append(ago)
            if other_total > 0:
                labels.append('Others')
                sizes.append(other_total)

            if not sizes:
                logger.warning("No product counts to plot for product pie chart")
                return None

            # Plot pie chart
            plt.style.use('default')
            fig, ax = plt.subplots(figsize=(6, 6), dpi=self.dpi)
            colors = ['#ff9999', '#66b3ff', '#99ff99']
            wedges, texts, autotexts = ax.pie(
                sizes,
                labels=labels,
                autopct='%1.1f%%',
                startangle=140,
                colors=colors[:len(sizes)],
                textprops={'color': self.text_color}
            )

            ax.axis('equal')  # Equal aspect ensures that pie is drawn as a circle.
            ax.set_title('Product Distribution (PMS / AGO / Others)', fontsize=12, color=self.text_color)

            # Save to bytes
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='PNG', dpi=self.dpi, bbox_inches='tight', facecolor='white')
            img_buffer.seek(0)
            chart_bytes = img_buffer.getvalue()

            plt.close(fig)
            img_buffer.close()

            logger.info('Generated product distribution pie chart')
            return chart_bytes

        except Exception as e:
            logger.error(f"Failed to generate product pie chart: {e}")
            return None
    
    def extract_product_counts_from_df(self, df: pd.DataFrame) -> Dict[str, int]:
        """Extract counts of product types (e.g., PMS, AGO) from a DataFrame's 'products' column."""
        counts = {}
        try:
            if df is None or df.empty:
                return counts

            # Find candidate columns that might contain product names
            product_cols = [c for c in df.columns if c.upper() in ('PRODUCTS', 'PRODUCT', 'PRODUCT_NAME')]
            if not product_cols:
                # Try heuristics: look for columns containing 'product' substring
                product_cols = [c for c in df.columns if 'product' in c.lower()]

            if not product_cols:
                return counts

            col = product_cols[0]
            series = df[col].dropna().astype(str).str.strip()
            for val in series:
                key = val.upper()
                # Normalize common names
                if 'AGO' in key:
                    label = 'AGO'
                elif 'PMS' in key or 'PETROL' in key or 'GASOLINE' in key:
                    label = 'PMS'
                else:
                    label = key
                counts[label] = counts.get(label, 0) + 1
        except Exception as e:
            logger.error(f"Error extracting product counts: {e}")
        return counts
