class TokenCounter:
    """Simple class to track token usage across LLM calls."""
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        
    def add_usage(self, input_tokens, output_tokens):
        """Add token usage from a single LLM call."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.call_count += 1
        
    def get_total_tokens(self):
        """Get total tokens consumed."""
        return self.total_input_tokens + self.total_output_tokens
        
    def get_summary(self):
        """Get a summary of token usage."""
        return {
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_tokens': self.get_total_tokens(),
            'call_count': self.call_count
        }
        
    def print_summary(self):
        """Print a formatted summary of token usage."""
        summary = self.get_summary()
        print(f"\n=== TOKEN USAGE SUMMARY ===")
        print(f"Total Input Tokens: {summary['total_input_tokens']:,}")
        print(f"Total Output Tokens: {summary['total_output_tokens']:,}")
        print(f"Total Tokens: {summary['total_tokens']:,}")
        print(f"LLM Calls: {summary['call_count']}")
        print(f"Average Tokens per Call: {summary['total_tokens'] / max(summary['call_count'], 1):.1f}")
        print("=" * 30)


