"""
Phase 7 frozen correctness evaluation — Knowledge Engine (V1 baseline / V2 target).
════════════════════════════════════════════════════════════════════════════════════
The EXACT 53 questions and repository-grounded ground truth from the Phase 7A audit,
persisted as a repeatable fixture. Ground truth priority: canonical vendored ODA
contracts → canonical ingested OpenAPI specs → repository evidence. NEVER derived from
an LLM answer. Do not edit questions or make them easier.

Auto-classification per question via:
  expect  — every substring must appear (case-insensitive)   → CORRECT
  forbid  — none may appear                                   → else WRONG_SPEC/HALLUCINATION
  abstain — the answer must decline for lack of evidence      → HONEST_ABSTENTION (== correct)
  major   — the answer must reflect this major and no other   → else WRONG_VERSION

Run:  venv/bin/python eval/phase7_eval.py            (hits live /query, deep, no_cache)
"""
import json, re, sys, time, urllib.request

API = "http://localhost:8000/query"

# (category, question, {expect?, forbid?, abstain?, major?})
Q = [
 ("A_identity","What is TMF642?",{"expect":["alarm"],"forbid":["service order","payment"]}),
 ("A_identity","What domain does TMF669 cover?",{"expect":["party role"]}),
 ("A_identity","What is TMF630?",{"forbid":["service order management"],"abstain":True}),
 ("A_identity","What is TMF622?",{"expect":["product order"]}),
 ("A_identity","What does TMF620 manage?",{"expect":["product catalog"]}),
 ("B_version","What version of TMF642 is required by TMFC043?",{"expect":["tmf642","v4"],"forbid":["v5"]}),
 ("B_version","Does TMFC027 use a v4 or v5 mandatory API?",{"expect":["tmf760","v5"]}),
 ("B_version","What are the mandatory attributes of an Alarm in TMF642 v4?",{"expect":["alarmtype","state","perceivedseverity"],"major":"4"}),
 ("B_version","In TMF669 v4, what fields identify a PartyRole?",{"expect":["name","roletype"]}),
 ("B_version","What is the difference between TMF642 v4 and v5?",{"expect":["v4","v5"]}),
 ("C_schema","What mandatory fields does TMF622 Product Order require?",{"expect":["productorderitem"]}),
 ("C_schema","What are the required attributes of Alarm?",{"expect":["alarmtype","state"]}),
 ("C_schema","What fields are required to create a PartyRole in TMF669?",{"expect":["partyrole","name"]}),  # version-agnostic: 'name' is required in v4 AND v5 (roleType is v4-specific)
 ("C_schema","What mandatory fields does TMF641 Service Order require?",{"expect":["serviceorderitem"]}),
 ("C_schema","What are the required fields of a ProductOrder item?",{"expect":["productoffering"]}),
 ("D_ops","How do I create an alarm?",{"expect":["alarm"],"forbid":["work order"]}),
 ("D_ops","Does TMF669 support DELETE for PartyRole?",{"expect":["partyrole"]}),
 ("D_ops","What operations does TMF642 support for alarms?",{"expect":["alarm"]}),
 ("E_oda","What mandatory APIs does TMFC043 expose?",{"expect":["tmf642","tmf669"],"forbid":["workorder","work order"]}),
 ("E_oda","What does TMFC061 expose?",{"expect":["tmf713","tmf669"],"forbid":["product catalog"]}),
 ("E_oda","What mandatory APIs does TMFC001 expose?",{"expect":["tmf620","tmf669"],"forbid":["workorder"]}),
 ("E_oda","What mandatory APIs does TMFC027 expose?",{"expect":["tmf679","tmf760","tmf669"]}),
 ("E_oda","What is the version of TMFC031?",{"expect":["3.0.0"]}),
 ("F_dep","Does TMFC043 depend on another API?",{"expect":["no dependent"],"forbid":["tmf641"]}),
 ("F_dep","What APIs does TMFC001 depend on?",{"expect":["tmfc001"]}),
 ("F_dep","Does TMFC014 have any dependent APIs?",{"expect":["no dependent"]}),
 ("G_events","What events does TMFC001 publish?",{"expect":["3"],"forbid":["couldn't find","tmf641 service order publishes"]}),
 ("G_events","Does TMFC022 publish events?",{"expect":["0"],"forbid":["tmf642 publishes"]}),
 ("G_events","How many events does TMFC043 subscribe to?",{"expect":["12"]}),
 ("H_cross","How does TMF669 relate to TMFC043?",{"expect":["tmf669"]}),
 ("H_cross","Which component owns fault management?",{"expect":["tmfc043"]}),
 ("H_cross","Which ODA component owns alarm management?",{"expect":["tmfc043"]}),
 ("H_cross","Which ODA component exposes TMF642?",{"expect":["tmfc043"]}),
 ("I_adv","Tell me about Alarm.",{"expect":["alarm"],"forbid":["don't have enough information"]}),
 ("I_adv","What is the fault API?",{"expect":["alarm"],"forbid":["don't have enough information"]}),
 ("I_adv","Which party API should I use?",{"expect":["party"]}),
 ("I_adv","What API handles tickets?",{"expect":["trouble ticket","tmf621"]}),
 ("J_neg","Does TMF642 define a payment method?",{"expect":["no"],"forbid":["yes, tmf642 defines a payment"]}),
 ("J_neg","Does TMFC043 expose TMF622?",{"expect":["tmf642","tmf669"],"forbid":["yes","exposes the product order"]}),
 ("J_neg","What is the mandatory quantum API in TM Forum?",{"abstain":True,"forbid":["is the product catalog","is the workorder","is the tmf"]}),
 ("J_neg","Does TMFC043 expose a billing API?",{"expect":["tmf642","tmf669"],"forbid":["applied customer billing rate"]}),
 ("J_neg","Which TM Forum API defines cryptocurrency wallets?",{"abstain":True,"forbid":["defines cryptocurrency wallets"]}),
 ("A_identity","What is TMF666?",{"expect":["account"]}),
 ("A_identity","What is TMF637?",{"expect":["product inventory"]}),
 ("B_version","Is TMF760 a v4 or v5 API in TMFC027?",{"expect":["v5"]}),
 ("C_schema","What identifies an Alarm uniquely?",{"expect":["id"]}),
 ("E_oda","What is the functional block of TMFC043?",{"expect":["production"],"forbid":["intelligence"]}),
 ("E_oda","What is the mandatory security API for every ODA component?",{"expect":["tmf669"]}),
 ("H_cross","What is the relationship between TMF642 and fault management?",{"expect":["alarm"]}),
 ("I_adv","Alarm attributes?",{"expect":["alarm"],"forbid":["product inventory"]}),
 ("J_neg","Does TMF669 manage alarms?",{"expect":["no"],"forbid":["yes, tmf669 manages alarm"]}),
 ("D_ops","How do I acknowledge an alarm in TMF642?",{"expect":["ack"]}),
 ("C_schema","What are the mandatory attributes of a ServiceOrder?",{"expect":["serviceorderitem"]}),
]

_ABSTAIN_MARKERS = ("don't have authoritative", "no authoritative", "won't answer", "won't guess",
                    "not contain", "can't give a reliable", "no matching", "won't infer",
                    "don't have enough information", "couldn't map", "not explicitly mentioned",
                    "not mentioned", "no mandatory quantum", "not defined in", "does not define")

def classify(ans: str, chk: dict) -> str:
    a = (ans or "").lower()
    abstained = any(m in a for m in _ABSTAIN_MARKERS)
    if chk.get("abstain"):
        return "HONEST_ABSTENTION" if abstained else "WRONG"
    for f in chk.get("forbid", []):
        if f.lower() in a:
            return "WRONG_SPEC"
    if chk.get("major"):
        # must not cite a different major as the answer's version
        other = {"4":"v5","5":"v4"}.get(chk["major"])
        if other and re.search(r"\b"+other+r"\b", a) and ("v"+chk["major"]) not in a:
            return "WRONG_VERSION"
    if all(e.lower() in a for e in chk.get("expect", [])):
        return "CORRECT"
    if abstained:
        return "REFUSED_DESPITE_EVIDENCE"
    return "PARTIALLY_CORRECT"

def run():
    out = []
    for i,(cat,q,chk) in enumerate(Q):
        body = json.dumps({"question":q,"mode":"deep","no_cache":True,"top_k":8}).encode()
        try:
            r = json.loads(urllib.request.urlopen(
                urllib.request.Request(API,data=body,headers={"Content-Type":"application/json"}),timeout=180).read())
            cls = classify(r.get("answer",""), chk)
            out.append({"i":i,"cat":cat,"q":q,"cls":cls,"chunks":r.get("chunks_retrieved"),
                        "sources":[s.get("file") for s in r.get("sources",[])][:4],
                        "answer":(r.get("answer") or "")[:200]})
        except Exception as e:
            out.append({"i":i,"cat":cat,"q":q,"cls":"ERROR","err":str(e)[:150]})
        print(f"[{i+1}/{len(Q)}] {cat:11s} {out[-1]['cls']:22s} {q[:52]}")
        json.dump(out, open("/tmp/phase7_v2_results.json","w"), indent=1)
    from collections import Counter
    c = Counter(r["cls"] for r in out)
    correct = c.get("CORRECT",0)+c.get("HONEST_ABSTENTION",0)
    print("\n== CLASSIFICATION ==")
    for k,v in c.most_common(): print(f"  {k:26s} {v}")
    print(f"\nSTRICT CORRECT (CORRECT+HONEST_ABSTENTION): {correct}/{len(Q)} = {100*correct/len(Q):.1f}%")

if __name__ == "__main__":
    run()
