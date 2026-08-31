from typing import List, Dict, Any, Optional

class RoutingPolicyEngine:
    def __init__(self, adapter_cache: Dict[str, Any]):
        """
        Initialize with a cache of available models and their metadata.
        adapter_cache format: { "model_id": {"capabilities": ["cap1", "cap2"], "cost": 0.05, ...} }
        """
        self.adapter_cache = adapter_cache

    def score_models(self, required_capabilities: List[str], max_cost: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Score models based on capabilities and cost constraints.
        """
        scored_models = []
        for model_id, model_info in self.adapter_cache.items():
            capabilities = model_info.get("capabilities", [])
            cost = model_info.get("cost", float('inf'))
            
            # Check constraints
            if max_cost is not None and cost > max_cost:
                continue
                
            has_all_caps = all(cap in capabilities for cap in required_capabilities)
            if not has_all_caps:
                continue
                
            # Score calculation: lower cost gives higher score
            score = 1.0 / (cost + 1.0)
            
            scored_models.append({
                "model_id": model_id,
                "model_info": model_info,
                "score": score
            })
            
        # Sort by score descending
        scored_models.sort(key=lambda x: x["score"], reverse=True)
        return scored_models

    def get_best_match(self, required_capabilities: List[str], max_cost: Optional[float] = None) -> Optional[str]:
        """
        Return the best matching model ID based on the constraints.
        """
        scored = self.score_models(required_capabilities, max_cost)
        if scored:
            return scored[0]["model_id"]
        return None
        
    def get_with_graceful_degradation(self, required_capabilities: List[str], max_cost: Optional[float] = None, unavailable_models: Optional[List[str]] = None) -> Optional[str]:
        """
        Return the best matching model, falling back to the next best if the best is unavailable.
        """
        unavailable_models = unavailable_models or []
        scored = self.score_models(required_capabilities, max_cost)
        
        for model in scored:
            if model["model_id"] not in unavailable_models:
                return model["model_id"]
                
        return None
