class HypothesisCriticAgent:
    def __init__(self, state):
        self.state = state

    def analyze(self):
        """
        Review the evidence collected so far
        and produce hypotheses and unknowns.
        """

        if self.state.top_segment is None:
            return {
                "status": "insufficient_evidence",
                "message": "A segment analysis is required before forming a hypothesis."
            }

        segment = self.state.top_segment

        hypothesis = (
            f"Payment failures may be contributing to the conversion "
            f"decline in the {segment['platform']} + "
            f"{segment['customer_type']} + "
            f"{segment['payment_method']} segment."
        )

        self.state.add_hypothesis(hypothesis)

        self.state.add_unknown(
            "The evidence does not establish that payment failures caused "
            "the conversion decline."
        )

        if self.state.country_evidence is not None:
            self.state.add_unknown(
                "The deterioration appears across countries, but the "
                "underlying payment failure pattern is not yet known."
            )

        if self.state.time_evidence is not None:
            self.state.add_unknown(
                "The timing of the change is visible, but the specific "
                "event or failure mechanism behind the change is unknown."
            )

        return {
            "hypothesis": hypothesis,
            "unknowns": self.state.unknowns
        }