# -*- coding: utf-8 -*-
import sqlite3

def test_diag_fp_storage(db, seeded, compiler):
    r1 = compiler.compile(seeded["evidence_id"], actor_id="system:compiler")
    rows = db.execute("SELECT unit_id, content_fingerprint FROM akb_semantic_units").fetchall()
    print("\nDB fp rows:", [(r["unit_id"][-8:], (r["content_fingerprint"] or "NONE")[:8]) for r in rows])
    print("r1 fp:", r1.fingerprint[:16], "| units fp:", [u.content_fingerprint[:8] if u.content_fingerprint else None for u in r1.units])
    print("in_transaction:", db.in_transaction)
    hit = db.execute("SELECT unit_id FROM akb_semantic_units WHERE content_fingerprint=?",
                     (r1.fingerprint,)).fetchone()
    print("hit query:", hit)
    assert hit is not None