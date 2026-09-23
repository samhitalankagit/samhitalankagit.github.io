class InvestigationState:
    def __init__(self, question):
        self.question = question

        self.signal = None
        self.top_segment = None
        self.country_evidence = None
        self.time_evidence = None

        self.hypotheses = []
        self.unknowns = []

        self.investigations_run = []

        self.next_investigation = None

    def add_investigation(self, name):
        self.investigations_run.append(name)

    def add_hypothesis(self, hypothesis):
        self.hypotheses.append(hypothesis)

    def add_unknown(self, unknown):
        self.unknowns.append(unknown)

    def summary(self):
        return {
            "question": self.question,
            "signal": self.signal,
            "top_segment": self.top_segment,
            "country_evidence": self.country_evidence,
            "time_evidence": self.time_evidence,
            "hypotheses": self.hypotheses,
            "unknowns": self.unknowns,
            "investigations_run": self.investigations_run,
            "next_investigation": self.next_investigation
        }