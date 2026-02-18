"""
LLM service wrapper for document processing.
Supports OpenAI, Ollama (Llama), and other providers.
"""
import json
import re
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Wrapper for LLM API calls with structured output support."""
    
    def __init__(self):
        """Initialize LLM client based on configuration."""
        self.client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL  # None for OpenAI, custom for Ollama
        )
        self.model = settings.LLM_MODEL
        self.is_ollama = settings.LLM_BASE_URL and "ollama" in settings.LLM_BASE_URL.lower()
        
        logger.info(f"LLM Service initialized: model={self.model}, provider={'Ollama' if self.is_ollama else 'OpenAI'}")
    
    def call_llm(
        self, 
        prompt: str, 
        system_prompt: str,
        response_format: str = "json",
        temperature: float = 0.0,
        max_tokens: int = 2000
    ) -> str:
        """
        Call LLM with given prompts and return response.
        
        Args:
            prompt: User prompt/content to process
            system_prompt: System instructions
            response_format: "json" for JSON mode, "text" for plain text
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            max_tokens: Maximum tokens in response
            
        Returns:
            LLM response as string
            
        Raises:
            Exception: If API call fails
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            # Build kwargs for API call
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # OpenAI supports structured JSON mode
            # Ollama/Llama does not - we rely on prompt engineering instead
            if response_format == "json" and not self.is_ollama:
                kwargs["response_format"] = {"type": "json_object"}
            
            logger.debug(f"Calling LLM with model={self.model}, temp={temperature}, max_tokens={max_tokens}")
            
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            
            logger.debug(f"LLM response received: {len(content)} characters")
            
            return content
            
        except Exception as e:
            logger.error(f"LLM API call failed: {str(e)}", exc_info=True)
            raise Exception(f"LLM API call failed: {str(e)}")
    
    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON response from LLM with robust error handling.
        Handles markdown code blocks and other LLM artifacts.
        
        Args:
            response: JSON string from LLM (may contain markdown)
            
        Returns:
            Parsed dictionary
            
        Raises:
            ValueError: If JSON parsing fails after cleanup attempts
        """
        try:
            # First attempt: direct parsing
            return json.loads(response)
        except json.JSONDecodeError:
            # LLM may have wrapped JSON in markdown - clean it up
            cleaned = self._clean_json_response(response)
            
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON after cleanup: {str(e)}")
                logger.error(f"Original response: {response[:500]}")
                logger.error(f"Cleaned response: {cleaned[:500]}")
                raise ValueError(f"Failed to parse LLM JSON response: {str(e)}")
    
    def _clean_json_response(self, response: str) -> str:
        """
        Clean LLM response to extract valid JSON.
        Removes markdown code blocks and other common artifacts.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Cleaned JSON string
        """
        # Remove leading/trailing whitespace
        response = response.strip()
        
        # Remove markdown code blocks (common in Ollama/Llama responses)
        # Patterns: ```json ... ```, ```... ```, or ``` ... ```
        response = re.sub(r'```json\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'```\s*', '', response)
        
        # Remove any text before the first {
        json_start = response.find('{')
        if json_start > 0:
            response = response[json_start:]
        
        # Remove any text after the last }
        json_end = response.rfind('}')
        if json_end >= 0:
            response = response[:json_end + 1]
        
        return response.strip()
    
    def validate_json_structure(
        self, 
        data: Dict[str, Any], 
        required_keys: Optional[list] = None
    ) -> bool:
        """
        Validate that parsed JSON has expected structure.
        
        Args:
            data: Parsed JSON dictionary
            required_keys: List of required top-level keys
            
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(data, dict):
            logger.warning(f"JSON response is not a dictionary: {type(data)}")
            return False
        
        if required_keys:
            missing_keys = [key for key in required_keys if key not in data]
            if missing_keys:
                logger.warning(f"Missing required keys: {missing_keys}")
                return False
        
        return True
    
    def extract_with_retry(
        self,
        prompt: str,
        system_prompt: str,
        max_retries: int = 2,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call LLM with automatic retry on JSON parsing failures.
        
        Args:
            prompt: User prompt
            system_prompt: System instructions
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments for call_llm
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            Exception: If all retry attempts fail
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"LLM call attempt {attempt + 1}/{max_retries + 1}")
                
                response = self.call_llm(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    **kwargs
                )
                
                data = self.parse_json_response(response)
                logger.info("========== LLM RAW TABLE DEBUG ==========")
                logger.info(f"Tables from LLM: {data.get('tables')}")
                logger.info(f"Table count: {len(data.get('tables', []))}")
                logger.info("=========================================")
                
                logger.info(f"Successfully extracted data on attempt {attempt + 1}")
                return data
                
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries:
                    # On retry, be more explicit about JSON format
                    if attempt == 0:
                        prompt += "\n\nIMPORTANT: Return ONLY valid JSON with no markdown, no code blocks, no explanations."
                    continue
                else:
                    break
        
        logger.error(f"All {max_retries + 1} attempts failed")
        raise Exception(f"LLM extraction failed after {max_retries + 1} attempts: {str(last_error)}")


# Global LLM service instance
llm_service = LLMService()