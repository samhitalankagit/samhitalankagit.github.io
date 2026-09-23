from trace_tools import (
    calculate_signal,
    find_top_segment,
    investigate_by_country,
    investigate_over_time
)


class InvestigatorAgent:
    def __init__(self, df, state):
        self.df = df
        self.state = state

    def run_signal_analysis(self):
        result = calculate_signal(self.df)

        self.state.signal = result
        self.state.add_investigation("signal_analysis")

        return result

    def run_segment_analysis(self):
        result = find_top_segment(self.df)

        self.state.top_segment = result
        self.state.add_investigation("segment_analysis")

        return result

    def run_country_analysis(self):
        segment = self.state.top_segment

        result = investigate_by_country(
            self.df,
            segment["platform"],
            segment["customer_type"],
            segment["payment_method"]
        )

        self.state.country_evidence = result
        self.state.add_investigation("country_analysis")

        return result

    def run_time_analysis(self):
        segment = self.state.top_segment

        result = investigate_over_time(
            self.df,
            segment["platform"],
            segment["customer_type"],
            segment["payment_method"]
        )

        self.state.time_evidence = result
        self.state.add_investigation("time_analysis")

        return result

    def choose_next_investigation(self):
        """
        Decide which investigation should happen next
        based on the evidence already collected.
        """

        if self.state.signal is None:
            return "signal_analysis"

        if self.state.top_segment is None:
            return "segment_analysis"

        if self.state.country_evidence is None:
            return "country_analysis"

        if self.state.time_evidence is None:
            return "time_analysis"

        return "investigation_complete"

    def investigate(self):
        """
        Run the next investigation selected by the agent.
        """

        next_step = self.choose_next_investigation()

        if next_step == "signal_analysis":
            return self.run_signal_analysis()

        if next_step == "segment_analysis":
            return self.run_segment_analysis()

        if next_step == "country_analysis":
            return self.run_country_analysis()

        if next_step == "time_analysis":
            return self.run_time_analysis()

        return {
            "status": "complete",
            "message": "Investigation has collected the planned evidence."
        }