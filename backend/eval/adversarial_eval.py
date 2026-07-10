"""
Phase 7B UNSEEN adversarial evaluation (Task 19) — 32 questions NOT used during
implementation, to detect benchmark overfitting. Reuses the phase7_eval classifier.
Ground truth: canonical resolver / ingested specs / repository evidence.

Run:  venv/bin/python eval/adversarial_eval.py   (backend on :8000)
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase7_eval import classify

API = "http://localhost:8000/query"

Q = [
 # unknown / absent TMF ids → must abstain, never invent from neighbours
 ("unknown","What is TMF999?",{"abstain":True}),
 ("unknown","What does TMF888 do?",{"abstain":True}),
 ("unknown","What are the mandatory fields of TMF950?",{"abstain":True}),
 # malformed ids → correct behavior is to DECLINE (not answer as a spec) → abstention expected
 ("malformed","Tell me about TMF6420.",{"abstain":True,"forbid":["tmf6420 is the"]}),
 ("malformed","What is TMF64?",{"forbid":["tmf64 is the standard"]}),
 # wrong/absent versions → abstain, never substitute another major
 ("wrong_ver","What are the mandatory fields of Alarm in TMF642 v9?",{"abstain":True}),
 ("wrong_ver","Show me TMF669 v3 PartyRole fields.",{"abstain":True}),
 # v4/v5 ambiguity handled honestly
 ("ambiguity","What changed in TMF620 between v4 and v5?",{"expect":["v4","v5"]}),
 # vague one-word entities
 ("vague","Alarm?",{"expect":["alarm"],"forbid":["don't have enough information"]}),
 ("vague","Catalog?",{"expect":["catalog"],"forbid":["don't have enough information"]}),
 # ODA component contract facts (resolver)
 ("oda","What does TMFC050 expose?",{"expect":["tmf680","tmf669"]}),
 ("oda","Does TMFC061 depend on anything?",{"expect":["tmfc061"]}),
 ("oda","What events does TMFC037 publish?",{"expect":["tmfc037"]}),
 ("oda","What functional block is TMFC009 in?",{"expect":["production"]}),
 ("oda","What mandatory APIs does TMFC024 expose?",{"expect":["tmf666","tmf669"]}),
 ("oda","Is TMFC999 a real ODA component?",{"abstain":True,"forbid":["yes, tmfc999","tmfc999 is the"]}),
 # cross-spec / reverse
 ("cross","Which ODA components use TMF669?",{"expect":["tmf669"]}),
 ("cross","Which ODA component owns product catalog?",{"expect":["tmfc001"]}),
 ("cross","Which component exposes TMF641?",{"expect":["tmfc007"]}),
 # false-premise → abstain / decline
 ("false","What is the mandatory blockchain API in TM Forum?",{"abstain":True,"forbid":["is the product catalog"]}),
 ("false","Which TMF API manages spaceships?",{"abstain":True}),
 ("false","Does TMF642 handle billing?",{"expect":["no"],"forbid":["yes, tmf642 handles billing"]}),
 ("false","Does TMF669 define alarms?",{"expect":["no"],"forbid":["yes, tmf669 defines alarm"]}),
 # nonexistent fields
 ("nofield","Is 'quantumField' a required attribute of an Alarm?",{"forbid":["yes, quantumfield is required"]}),
 ("nofield","Does ProductOrder require a 'cryptoWallet' field?",{"forbid":["yes","cryptowallet is required"]}),
 # TMF + MEF mixing → MEF must NOT surface as canonical TMF evidence
 ("mef","Is ipCommon part of TMF669?",{"forbid":["yes, ipcommon is part of tmf669"]}),
 ("mef","What is the LSO Sonata API in TM Forum?",{"abstain":True,"forbid":["lso sonata is a tm forum"]}),
 ("mef","How does TMF642 relate to carrierEthernet?",{"forbid":["carrierethernet is part of tmf642"]}),
 # identity sanity
 ("identity","What is TMF641?",{"expect":["service order"]}),
 ("identity","What domain is TMF632?",{"expect":["party"]}),
 # version-specific isolation
 ("version","In TMF642 v5, is 'state' still required for an Alarm?",{"expect":["5.0.1"],"forbid":["4.0.0"]}),  # must reflect v5 evidence, never v4
 ("oda","What is the version of TMFC012?",{"expect":["2.2.0"]}),
]

def run():
    out = []
    for i,(cat,q,chk) in enumerate(Q):
        body = json.dumps({"question":q,"mode":"deep","no_cache":True,"top_k":8}).encode()
        try:
            r = json.loads(urllib.request.urlopen(
                urllib.request.Request(API,data=body,headers={"Content-Type":"application/json"}),timeout=180).read())
            cls = classify(r.get("answer",""), chk)
            out.append({"i":i,"cat":cat,"q":q,"cls":cls,"answer":(r.get("answer") or "")[:170]})
        except Exception as e:
            out.append({"i":i,"cat":cat,"q":q,"cls":"ERROR","err":str(e)[:120]})
        print(f"[{i+1}/{len(Q)}] {out[-1]['cls']:22s} {q[:50]}")
        json.dump(out, open("/tmp/phase7_adv_results.json","w"), indent=1)
    from collections import Counter
    from phase7_eval import SUCCESS
    c = Counter(r["cls"] for r in out)
    good = sum(1 for r in out if r["cls"] in SUCCESS)   # CORRECT + EXPECTED_ABSTENTION
    n = len(out)
    print("\n== ADVERSARIAL (measured on final code + axiom_v2) ==", dict(c))
    print(f"  ADVERSARIAL SUCCESS       {good}/{n} = {100*good/n:.1f}%")
    print(f"  HALLUCINATION RATE        {c.get('HALLUCINATION',0)}/{n} = {100*c.get('HALLUCINATION',0)/n:.1f}%")
    print(f"  WRONG-SPEC RATE           {c.get('WRONG_SPEC',0)}/{n} = {100*c.get('WRONG_SPEC',0)/n:.1f}%")
    print(f"  WRONG-VERSION RATE        {c.get('WRONG_VERSION',0)}/{n} = {100*c.get('WRONG_VERSION',0)/n:.1f}%")
    print(f"  UNEXPECTED-ABSTENTION     {c.get('UNEXPECTED_ABSTENTION',0)}/{n} = {100*c.get('UNEXPECTED_ABSTENTION',0)/n:.1f}%")
    print("\n== NON-SUCCESS ==")
    for r in out:
        if r["cls"] not in SUCCESS:
            print(f"  [{r['i']}] {r['cls']:22s} {r['q'][:50]}")

if __name__ == "__main__":
    run()
