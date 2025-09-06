
import google.generativeai as genai
from app.config import CONFIG

class GeminiProcessor:
    def __init__(self):
        genai.configure(api_key=CONFIG.gemini.api_key)
        # Try different model names in order of preference
        model_names = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
        self.model = None
        
        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                print(f"Successfully initialized Gemini model: {model_name}")
                break
            except Exception as e:
                print(f"Failed to initialize model {model_name}: {e}")
                continue
        
        if self.model is None:
            raise Exception("Failed to initialize any Gemini model. Please check your API key and model availability.")

    def get_command_from_text(self, text: str, available_commands: list) -> str:
        """
        Uses Gemini to get a command from a natural language string.
        """
        prompt = f"""
        You are a helpful assistant for a Telegram bot. The bot has the following commands: {', '.join(available_commands)}.

        User's message: "{text}"

        Determine which command the user wants to execute based on their message. If the message clearly matches one of the commands, respond with the exact command name (e.g., '/start', '/help'). If it doesn't match any command or is a general conversation, respond with 'NO_COMMAND'.

        Examples:
        - "Hello" -> NO_COMMAND
        - "Show me the help" -> /help
        - "Check BRV number AS123" -> /check
        - "What is the status?" -> /status

        Respond with only the command name or 'NO_COMMAND'.
        """
        try:
            response = self.model.generate_content(prompt)
            command = response.text.strip()
            if command in available_commands or command == 'NO_COMMAND':
                return command
            else:
                return 'NO_COMMAND'
        except Exception as e:
            print(f"Error interacting with Gemini: {e}")
            return 'NO_COMMAND'

    def process_audio_message(self, audio_file_path: str, available_commands: list) -> str:
        """
        Process an audio message using Gemini to extract commands or respond.
        """
        try:
            # Upload the audio file to Gemini
            audio_file = genai.upload_file(audio_file_path)
            
            prompt = f"""
            You are a helpful assistant for a Telegram bot. The bot has the following commands: {', '.join(available_commands)}.

            The user sent an audio message. Transcribe the speech and determine if they want to execute a command.
            
            If the transcribed message clearly matches one of the commands, respond with the exact command name (e.g., '/start', '/help').
            If it doesn't match any command or is a general conversation, respond with 'NO_COMMAND'.
            
            Examples:
            - "Show me the help" -> /help
            - "Check the status" -> /status
            - "What are recent records?" -> /recent
            - "Hello" -> NO_COMMAND
            
            First, provide the transcription, then the command.
            Format: TRANSCRIPTION: [transcription]
            COMMAND: [command]
            """
            
            response = self.model.generate_content([prompt, audio_file])
            result = response.text.strip()
            
            # Extract command from response
            if 'COMMAND:' in result:
                command_line = result.split('COMMAND:')[-1].strip()
                if command_line in available_commands or command_line == 'NO_COMMAND':
                    return command_line
            
            return 'NO_COMMAND'
            
        except Exception as e:
            print(f"Error processing audio with Gemini: {e}")
            return 'NO_COMMAND'

