"""
Phase 7D — READ-ONLY authority & relationship-semantics eval (80 questions).
════════════════════════════════════════════════════════════════════════════
Audits whether the LIVE engine grounds answers at the RIGHT authority level and preserves
the EXACT relationship type the evidence proves. Ground truth is repository/index evidence,
NOT the chatbot's answer. No product code is modified; this is measurement only.

Heuristic auto-flags (red = an authority/relationship/constraint defect for THAT question;
'abstain' = honest evidence-absence). Full answers are captured for manual review.
"""
import json, re, sys, time, urllib.request
API = "http://localhost:8000/query"

_ABSTAIN = ("don't have authoritative", "no authoritative", "won't affirm", "won't guess",
            "only a lexical neighbour", "don't have enough information", "not a valid tm forum",
            "not a resolvable", "does not define", "not defined", "no explicit", "not specified",
            "not specify", "canonical evidence does not", "no evidence")

# (category, question, red_flags[], note). red_flags = substrings that, if present, indicate
# the specific authority/relationship/constraint error this question probes.
Q = [
 # A. GLOBAL DESIGN RULES — must not assert a TMF-wide normative rule from per-API specs / must not invent
 ("A_global","How do I paginate TM Forum API collections?",["0-based","zero-based","0-indexed"],"pagination global"),
 ("A_global","Are offsets zero-based in TM Forum APIs?",["yes","0-based","zero-based","0-indexed","starts at 0","index of 0"],"0-based unsupported"),
 ("A_global","Do all TM Forum APIs use limit and offset?",["yes, all","all tm forum apis use","every tm forum api"],"global generalization"),
 ("A_global","Are href values always URIs in TM Forum APIs?",["always","yes, href","all href"],"href-URI generalization"),
 ("A_global","Are IDs globally unique across TM Forum APIs?",["globally unique","yes, ids are","always unique"],"global uniqueness"),
 ("A_global","How should errors be represented across TM Forum APIs?",["all tm forum apis","every api returns"],"error global rule"),
 ("A_global","What is the expected PATCH behavior in TM Forum Open APIs?",["all tm forum apis follow","every api uses","identical patch"],"patch global"),
 ("A_global","How are fields selected in TM Forum APIs?",["all apis","every tm forum"],"fields selection global"),
 # B. API-SPECIFIC RULES — scoped facts (should be fine)
 ("B_api","How does pagination work in TMF622 v4?",[],"api-scoped ok"),
 ("B_api","Does TMF642 v4 define a limit query parameter?",[],"api-scoped"),
 ("B_api","What operations exist in TMF669 v4?",[],"operations"),
 ("B_api","Does TMF621 define a relatedEntity field?",[],"schema field presence"),
 ("B_api","What does TroubleTicket.relatedEntity represent?",["depends on","calls","runtime","integration with"],"relatedEntity semantics"),
 # C. SCHEMA / PROPERTY CONSTRAINTS — description vs validation constraint
 ("C_prop","What format is Alarm.id in TMF642 v4?",["uuid","uri","guid"],"id format speculation"),
 ("C_prop","Are there constraints (pattern, format, length) on ProductOrder.id in TMF622 v4?",["uuid","uri","likely","probably","expected to be a"],"constraint speculation"),
 ("C_prop","Does TMF622 v4 define a regex pattern for id?",["uuid","uri","pattern is"],"pattern absent"),
 ("C_prop","Is ProductOrder.id required in TMF622 v4?",[],"requiredness"),
 ("C_prop","What is the maxLength of TroubleTicket.description in TMF621?",["maxlength is","limited to","characters max"],"maxlength absent"),
 # D. CROSS-SPEC GENERALIZATION — must not infer global from 2-3 specs
 ("D_cross","Since TMF622 and TMF633 both use offset, do all TM Forum APIs use offset?",["yes","all tm forum","every api"],"generalization bait"),
 ("D_cross","Two APIs use limit — is limit a TM Forum standard?",["yes, it is a standard","all apis","tm forum standard"],"generalization"),
 # E. GUIDELINE VS IMPLEMENTATION
 ("E_guide","What is the normative TM Forum REST design guideline for pagination?",["shoppingcart","tmf663","offset=20&limit=10"],"normative vs impl"),
 ("E_guide","Which document defines the TM Forum REST API design rules?",["tmf622","tmf620","shopping cart"],"design authority"),
 # F. ABSENT CONSTRAINTS — correct = 'evidence does not define'
 ("F_absent","Does TMF642 v4 define a minLength for Alarm.alarmType?",["minlength is","at least"],"absent constraint"),
 ("F_absent","What is the enum of valid values for ProductOrder.id?",["enum","valid values are"],"no enum"),
 # G. FOLLOW-UP CONTEXT handled as single-shot (no history) — scope questions
 ("G_follow","In TMF622 v4, what format is the ProductOrder id — is it a UUID?",["yes","uuid","it is a uuid"],"followup uuid"),
 ("G_follow","Is the ProductOrder id format the same across all TM Forum APIs?",["yes","same across all","all tm forum"],"followup global"),
 # H. FRAMEWORK AUTHORITY — SID vs Open API vs ODA vs eTOM
 ("H_auth","What is the SID ABE for customer data?",["tmf629 - customer","defined in tmf629","tmf629 defines","the customer abe represents","tmf629 customer management"],"open api as SID"),
 ("H_auth","Does TMF629 define the Customer ABE in the SID?",["yes","tmf629 defines the customer abe","defines the sid"],"SID authority"),
 ("H_auth","Is a TMF Open API schema the same as the SID information model?",["yes","it is the sid","same as the sid model"],"openapi==SID"),
 ("H_auth","Which framework defines TM Forum business process definitions?",["tmf622","open api","tmf629"],"eTOM authority"),
 ("H_auth","Does eTOM define REST API operations?",["yes","etom defines rest"],"etom scope"),
 ("H_auth","Which source defines an ODA component's dependent APIs?",["tmf629","openapi schema","the open api"],"ODA authority"),
 ("H_auth","Does an ODA component YAML define Open API schema fields?",["yes","the yaml defines the fields"],"ODA vs schema"),
 ("H_auth","Can TMF622 be used as the authority for the SID entity hierarchy?",["yes","tmf622 defines the sid"],"openapi as SID authority"),
 ("H_auth","What is the SID Product ABE?",["tmf620 defines","defined in tmf620","the product abe is defined in tmf"],"open api as SID"),
 ("H_auth","What does the Information Framework say about the Service ABE?",["tmf633 defines","defined in tmf633","the service abe is"],"SID absent"),
 # I. RELATIONSHIP SEMANTICS (>=20)
 ("I_rel","If TMF621 references ProductOrder in a schema, does it depend on TMF622?",["yes","depends on tmf622","it depends on"],"schema-ref->dependency"),
 ("I_rel","Does TroubleTicket.relatedEntity mean TMF621 calls the related entity's API?",["yes","calls the","it calls"],"relatedEntity->call"),
 ("I_rel","Which APIs does TMF621 explicitly depend on?",["depends on tmf622","depends on tmf624","relies on"],"explicit dependency"),
 ("I_rel","Which ODA components expose TMF621?",["tmfc050","exposed by tmfc"],"exposure (none)"),
 ("I_rel","Is TMF621 part of the Product Recommendation component?",["yes","tmf621 is part of","exposed by product recommendation"],"part-of confusion"),
 ("I_rel","Does TMF621 call TMF624?",["yes","tmf621 calls tmf624","it calls tmf624"],"runtime call"),
 ("I_rel","What is the difference between a schema reference and an API dependency?",[],"concept (should explain)"),
 ("I_rel","If TroubleTicket contains a ProductRef, does that prove Product Inventory integration?",["yes","proves","it integrates with product inventory"],"ref->integration"),
 ("I_rel","Does an ODA dependent API imply every Open API operation calls that API?",["yes","every operation calls"],"dependent->every-op"),
 ("I_rel","Can a data-model relationship be presented as a runtime API integration?",["yes"],"data->runtime"),
 ("I_rel","Does relatedParty prove the Party Management API is called?",["yes","proves","party management api is called"],"relatedParty->call"),
 ("I_rel","Does an href value prove an HTTP dependency between APIs?",["yes","proves an http dependency","href proves"],"href->dependency"),
 ("I_rel","Does an entity reference establish API ownership?",["yes","establishes ownership","proves ownership"],"ref->ownership"),
 ("I_rel","If two APIs both use a Characteristic schema, are they dependent on each other?",["yes","they are dependent","depend on each other"],"shared-schema->dependency"),
 ("I_rel","Is a mandatory API the same as a dependent API in ODA?",["yes","they are the same","same thing"],"mandatory==dependent"),
 ("I_rel","Is component exposure the same as runtime invocation?",["yes","same as","exposure means it calls"],"exposure==invocation"),
 ("I_rel","Does TMFC050 depending on TMF621 mean TMF621 relies on Product Recommendation?",["yes","tmf621 relies on product recommendation","tmf621 depends on product recommendation"],"direction inversion"),
 ("I_rel","Is a dependent API the same as a schema dependency?",["yes","same as a schema"],"dependency==schema-ref"),
 ("I_rel","Does a ProductOrderRef in TroubleTicket prove Order Management orchestration?",["yes","proves orchestration","order management orchestration"],"ref->orchestration"),
 ("I_rel","What evidence is required to claim that API A calls API B?",[],"concept (should require explicit)"),
 ("I_rel","How does Trouble Ticket Open API interact with other APIs?",["depends on","relies on","calls","dependent api of","automated resolution"],"interaction collapse"),
 # J. ADVERSARIAL AUTHORITY / RELATIONSHIP BAIT
 ("J_bait","Since TMF622 uses strings for ids, all TM Forum ids are UUID strings, right?",["yes","correct","that's right","all tm forum ids are uuid"],"uuid bait"),
 ("J_bait","offset always starts at zero, correct?",["yes","correct","that's right","starts at zero"],"0-based bait"),
 ("J_bait","All TM Forum APIs support limit and offset, yes?",["yes","correct","all tm forum apis support"],"global bait"),
 ("J_bait","Every TM Forum API follows identical PATCH semantics, right?",["yes","correct","identical patch"],"patch bait"),
 ("J_bait","TMF629 defines the SID Customer ABE, correct?",["yes","correct","that's right","tmf629 defines the sid"],"SID bait"),
 ("J_bait","Since TMF621 contains ProductRef, it calls Product Inventory, right?",["yes","correct","it calls product inventory"],"ref-call bait"),
 ("J_bait","TMF621 depends on Product Recommendation, correct?",["yes","correct","tmf621 depends on product recommendation"],"dependency bait"),
 ("J_bait","relatedEntity is basically an API dependency, yes?",["yes","basically","correct","it is an api dependency"],"relatedEntity bait"),
 ("J_bait","An ODA dependent API is called by every operation, right?",["yes","correct","every operation"],"every-op bait"),
 ("J_bait","If the schema references Customer, the API depends on Customer Management, correct?",["yes","correct","depends on customer management"],"schema-ref bait"),
 ("J_bait","All TM Forum resource ids are UUIDs, aren't they?",["yes","aren't","all resource ids are uuid","they are uuids"],"uuid global bait"),
 ("J_bait","Every TM Forum API exposes a /hub for events, correct?",["yes","correct","every api exposes"],"hub global bait"),
 # extra global/constraint
 ("A_global","Is the offset parameter 0-based in TM Forum APIs?",["yes","0-based","zero-based","index of 0"],"0-based direct"),
 ("C_prop","Does Alarm.id in TMF642 follow a UUID format?",["yes","uuid","it follows a uuid"],"uuid direct"),
 ("H_auth","What is the SID ABE for product data?",["tmf620 defines","the product abe is defined in tmf620"],"SID product"),
 ("I_rel","Does TMF621 orchestrate other APIs?",["yes","it orchestrates","tmf621 orchestrates"],"orchestration claim"),
 ("B_api","What query parameters does TMF622 v4 support for listing product orders?",[],"api params ok"),
 ("F_absent","Does TMF669 v4 define a format constraint on PartyRole.id?",["uuid","uri","format is"],"absent format"),
]

def classify(ans, red):
    a = (ans or "").lower()
    abst = any(m in a for m in _ABSTAIN)
    hit = [r for r in red if r.lower() in a]
    if hit:
        return "RED:" + hit[0][:22]
    if abst:
        return "ABSTAIN/HEDGE"
    return "review"

def run():
    out=[]
    for i,(cat,q,red,note) in enumerate(Q):
        body=json.dumps({"question":q,"mode":"deep","no_cache":True,"top_k":8}).encode()
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(API,data=body,headers={"Content-Type":"application/json"}),timeout=180).read())
            cls=classify(r.get("answer",""),red)
            out.append({"i":i,"cat":cat,"q":q,"note":note,"cls":cls,"conf":(r.get("confidence") or {}).get("level"),
                        "sources":[s.get("file") for s in r.get("sources",[])][:3],"answer":(r.get("answer") or "")[:260]})
        except Exception as e:
            out.append({"i":i,"cat":cat,"q":q,"cls":"ERROR","err":str(e)[:120]})
        print(f"[{i+1}/{len(Q)}] {out[-1]['cls'][:26]:26s} {cat:9s} {q[:44]}")
        json.dump(out,open("/tmp/authority_eval.json","w"),indent=1)
    from collections import Counter
    red=sum(1 for r in out if r['cls'].startswith('RED'))
    print(f"\nTOTAL {len(out)} | RED-FLAGGED (authority/relationship/constraint defect): {red} | by cat:",
          dict(Counter(r['cat'][0] for r in out if r['cls'].startswith('RED'))))

if __name__=="__main__": run()
