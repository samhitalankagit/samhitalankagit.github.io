class PlannerAgent:
    def __init__(self, state):
        self.state = state

    def plan_next_investigation(self):
        """
        Decide what evidence should be investigated next
        based on the current state.
        """

        if self.state.top_segment is None:
            return {
                "next_investigation": "segment_analysis",
                "reason": "We need to identify where the conversion decline is concentrated."
            }

        if self.state.country_evidence is None:
            return {
                "next_investigation": "country_analysis",
                "reason": "We need to determine whether the decline is isolated to a specific country."
            }

        if self.state.time_evidence is None:
            return {
                "next_investigation": "time_analysis",
                "reason": "We need to determine when the deterioration began."
            }

        if self.state.time_evidence is not None:
            return {
                "next_investigation": "payment_failure_pattern",
                "reason": (
                    "The decline appears across countries and begins abruptly. "
                    "The next useful investigation is to identify whether the "
                    "increase in payment failures follows a specific pattern."
                )
            }

        return {
            "next_investigation": "investigation_complete",
            "reason": "The available evidence has been investigated."
        }