from . import confidence, executor, explain, feedback, intent_parser, sql_builder


class QueryEngine:
    def __init__(self, conn, schema, dataset_dir):
        self.conn = conn
        self.schema = schema
        self.feedback_entries = feedback.load(dataset_dir)

    def answer(self, query):
        intent = intent_parser.parse(query, self.schema)
        sql, kind = sql_builder.build(intent)

        try:
            result = executor.run(self.conn, sql, kind)
            error = None
        except Exception as exc:
            result = None
            error = str(exc)

        fb_adjustment = feedback.adjustment(query, self.feedback_entries)
        conf = confidence.score(intent, result, kind, feedback=fb_adjustment)
        if error:
            conf = 0.0

        explanation = explain.build(query, intent, sql, result) if not error else (
            f"The generated SQL failed to execute: {error}"
        )

        return {
            "query": query,
            "generated_logic": sql,
            "result": result if not error else None,
            "confidence_score": conf,
            "explanation": explanation,
        }
