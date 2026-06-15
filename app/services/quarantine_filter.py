from app.services.heuristic_filter import HeuristicPreFilter

class QuarantineHeuristicFilter:
    """
    Heuristic filter used during the Quarantine decision phase.
    If ClamAV/YARA flags a file, this filter determines if we actually need AI
    to act as the second judge, or if we can bypass AI to save quota.
    """
    
    def __init__(self, pre_filter: HeuristicPreFilter):
        self.pre_filter = pre_filter
        self.malicious_threshold = 3
        
    def evaluate(self, content: str, file_ext: str) -> str:
        """
        Returns an action string: "QUARANTINE_DIRECT" or "ASK_AI"
        """
        scan_result = self.pre_filter.scan_content(content, file_ext)
        trigger_count = len(scan_result["triggers"])
        
        if trigger_count >= self.malicious_threshold:
            return "QUARANTINE_DIRECT"
            
        return "ASK_AI"
