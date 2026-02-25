"""
Behavioral Simulation Metrics Tracker.

Tracks the quality of the assistant's insights independent of PnL:
- Noise Ratio (Too many alerts?)
- Whip-sawing / Flip-flopping (Changing mind too fast?)
- Meaningful Alert % (Did the market actually move after the alert?)
"""

from typing import List, Dict

class SimulationMetrics:
    def __init__(self):
        self.total_alerts = 0
        self.flip_flops = 0
        self.meaningful_alerts = 0
        self.signals_fired = []  # List of dicts (idx, price, direction, time)
        
    def record_signal(self, direction: str, confidence: int, price: float, bar_idx: int, timestamp: str):
        """Records a high-confidence signal fired by the Orchestrator."""
        if direction not in ("BUY", "SELL"):
            return
            
        self.total_alerts += 1
        
        # Check for flip-flop: A signal in the opposite direction within 12 bars (e.g. 12 hours)
        if self.signals_fired:
            last_sig = self.signals_fired[-1]
            if last_sig["direction"] != direction and (bar_idx - last_sig["bar_idx"] <= 12):
                self.flip_flops += 1
                
        self.signals_fired.append({
            "direction": direction,
            "confidence": confidence,
            "price": price,
            "bar_idx": bar_idx,
            "timestamp": timestamp,
            "graded": False
        })
        
    def grade_meaningful_alerts(self, current_price: float, current_bar_idx: int):
        """
        Called on every bar. Checks all ungraded past signals to see if 
        they resulted in a 20+ pip move in their favor within 24 bars.
        """
        for sig in self.signals_fired:
            if sig["graded"]:
                continue
                
            bars_elapsed = current_bar_idx - sig["bar_idx"]
            if bars_elapsed > 24:
                # Expired without hitting 20 pip movement -> Noise
                sig["graded"] = True
                continue
                
            diff = (current_price - sig["price"]) * 10000
            if sig["direction"] == "BUY" and diff >= 20.0:
                self.meaningful_alerts += 1
                sig["graded"] = True
            elif sig["direction"] == "SELL" and diff <= -20.0:
                self.meaningful_alerts += 1
                sig["graded"] = True

    def get_report(self) -> str:
        if self.total_alerts == 0:
            return "No alerts fired. Simulator might be broken or strategy too strict."
            
        noise_ratio = ((self.total_alerts - self.meaningful_alerts) / self.total_alerts) * 100
        meaningful_ratio = (self.meaningful_alerts / self.total_alerts) * 100
        
        lines = [
            "📊 **Behavioral Simulation Metrics**",
            f"🔔 Total Alerts Fired: {self.total_alerts}",
            f"📉 Meaningful Alerts (>20pips action): {self.meaningful_alerts} ({meaningful_ratio:.1f}%)",
            f"🗑️ Noise Ratio (False Alarms): {noise_ratio:.1f}%",
            f"🔄 Flip-flops (Opinion changed <12 bars): {self.flip_flops}"
        ]
        
        # Qualitative grade
        if noise_ratio > 60:
            lines.append("\n⚠️ **Diagnosis:** The assistant is too noisy. Likely overreacting to M15 noise. Needs higher confidence thresholds.")
        elif self.flip_flops > (self.total_alerts * 0.2):
            lines.append("\n⚠️ **Diagnosis:** The assistant is flip-flopping too often. Memory/context injection might be losing track of the higher timeframe trend.")
        elif meaningful_ratio >= 60:
            lines.append("\n✅ **Diagnosis:** Excellent behavioral profile. Assistants insights are highly predictive and stable.")
            
        return "\n".join(lines)
