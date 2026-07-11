"""
Phase 7E — Task 15 live acceptance (20 questions). Semantics, not wording.
Run against axiom_v2, deep model, no_cache. Captures full answers + confidence for review.
Run:  venv/bin/python eval/acceptance_7e.py   (backend on :8000)
"""
import json, urllib.request
API = "http://localhost:8000/query"

# (id, question, forbid_positive[], expect_markers[], note)
Q = [
 ("A1","How do I handle pagination in TM Forum Open APIs?",
   ["zero-based","0-based","0-indexed"],["normative","specific","scope","don't have","not have"],"scope or abstain; no 0-based"),
 ("A2","Are offsets zero-based across all TM Forum APIs?",
   ["zero-based","0-based","0-indexed","starts at zero"],["can't state","normative","not have","don't have"],"no universal claim"),
 ("A3","Do all TM Forum APIs use limit and offset?",
   ["yes, all","all tm forum apis use","every tm forum api"],["can't state","normative","scope","not have"],"no impl→global"),
 ("B4","Are there any specific formats or constraints for the id field in TMF622 Product Ordering?",
   ["uuid","uri","likely","probably","expected to be"],["does not define","type: string","not define","no explicit"],"exact only"),
 ("B5","Is ProductOrder.id a UUID?",
   ["uuid"],["does not define","not define","no explicit","type: string"],"only yes if format proves"),
 ("B6","Does href have URI format validation?",
   ["yes, href has uri format","format: uri is defined"],["hyperlink","depends","not define","specific"],"descriptive vs format:uri"),
 ("C7","What is the SID ABE for customer data?",
   ["tmf629 - customer","defined in tmf629","tmf629 defines"],["don't have","sid","information framework","different authority"],"SID absent → abstain"),
 ("C8","Does TMF629 define the Customer ABE?",
   ["yes","tmf629 defines the customer abe","defines the sid"],["open api","different authority","don't have","not the sid"],"Open API ≠ SID"),
 ("C9","What eTOM process handles trouble tickets?",
   ["tmf621","tmf629"],["don't have","etom","business process","not have"],"eTOM absent → abstain"),
 ("D10","How does Trouble Ticket Open API interact with other APIs?",
   ["relies on","automated resolution","curl","http://"],["different kinds","data-model","no explicit integration","component"],"separate types, no runtime, no curl"),
 ("D11","Does TMF621 depend on Product Recommendation?",
   ["yes","tmf621 depends on product recommendation"],["open api","component → api","not reverse","do not declare"],"no inversion"),
 ("D12","Does TMFC050 depend on TMF621?",
   [],["tmf621"],"ODA contract, correct direction (yes)"),
 ("D13","If TMF621 references Product, does it depend on the Product API?",
   ["yes","it depends on"],["data-model","not an api dependency","schema reference","does not"],"ref≠dependency"),
 ("D14","Does relatedEntity mean TMF621 calls the related entity's API?",
   ["yes","calls the","it calls"],["data-model","association","not","no explicit"],"no runtime"),
 ("D15","Does relatedParty prove Party Management is invoked?",
   ["yes","party management api is called","is invoked"],["association","not","no explicit","data-model"],"no runtime"),
 ("D16","Is a dependent API called by every operation of an ODA component?",
   ["yes","every operation calls"],["not","no explicit","contract","component-level"],"no every-op"),
 ("D17","Is a mandatory API the same as a dependent API?",
   ["yes","the same","same thing"],["different","expose","consume","not"],"mandatory≠dependent"),
 ("D18","Which ODA components expose TMF621?",
   ["tmfc050 exposes tmf621"],["no canonical","no oda component","expose"],"none exposes (correct)"),
 ("D19","Which ODA components depend on TMF621?",
   [],["tmfc050","component → api","consume"],"TMFC050 depends (correct direction)"),
 ("D20","What evidence is required to claim API A calls API B?",
   ["schema reference is sufficient","relatedentity is sufficient"],["explicit","integration evidence","not sufficient"],"requires explicit integration"),
]

def check(q_forbid, expect, ans):
    a = (ans or "").lower()
    bad = [f for f in q_forbid if f in a and not a.split(f)[0].rstrip().endswith(("not","n't","never","no","without"))]
    # affirmation guard for the bait/relationship refusals
    starts_yes = a.lstrip("* ").startswith(("yes,","yes.","yes —","yes -","correct"))
    hit_expect = any(e in a for e in expect) if expect else True
    ok = (not bad) and hit_expect and not (starts_yes and q_forbid)
    return "PASS" if ok else "REVIEW", bad

def run():
    out=[]
    for qid,q,forbid,expect,note in Q:
        body=json.dumps({"question":q,"mode":"deep","no_cache":True,"top_k":8}).encode()
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(API,data=body,headers={"Content-Type":"application/json"}),timeout=200).read())
            ans=r.get("answer","") or ""; conf=(r.get("confidence") or {}).get("level")
            verdict,bad=check(forbid,expect,ans)
        except Exception as e:
            ans="";conf=None;verdict="ERROR";bad=[str(e)[:80]]
        out.append({"id":qid,"q":q,"verdict":verdict,"conf":conf,"note":note,"bad":bad,"answer":ans})
        json.dump(out,open("/tmp/acceptance_7e.json","w"),indent=1)
        print(f"{qid:4s} {verdict:6s} conf={str(conf):6s} {q[:46]}")
    p=sum(1 for o in out if o['verdict']=='PASS')
    print(f"\nACCEPTANCE: {p}/{len(Q)} PASS  ({sum(1 for o in out if o['verdict']=='REVIEW')} review, {sum(1 for o in out if o['verdict']=='ERROR')} error)")

if __name__=="__main__": run()
