"""Asks each Genie agent its questions and prints the SQL, the first rows and any error.

Usage: python tests/genie_check.py --profile <profile> --space <space_id> "question" ["question" ...]"""
import argparse

from databricks.sdk import WorkspaceClient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile")
    ap.add_argument("--space", required=True)
    ap.add_argument("questions", nargs="+")
    a = ap.parse_args()
    w = WorkspaceClient(profile=a.profile)
    for q in a.questions:
        m = w.genie.start_conversation_and_wait(a.space, q)
        print(f"\n### {q}\nstatus: {m.status}")
        for att in m.attachments or []:
            if att.text:
                print("text:", (att.text.content or "")[:400])
            if att.query:
                print("sql:", " ".join(att.query.query.split())[:700])
                r = w.genie.get_message_attachment_query_result(a.space, m.conversation_id, m.id, att.attachment_id)
                res = r.statement_response.result
                cols = [c.name for c in r.statement_response.manifest.schema.columns]
                print("cols:", cols)
                for row in (res.data_array or [])[:4]:
                    print("  ", row)
                print("rows:", r.statement_response.manifest.total_row_count)
        if m.error:
            print("error:", m.error)


if __name__ == "__main__":
    main()
