import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RECORDS = ROOT / "evaluation/datasets/feedback-decision-1.0.0/records.jsonl"
OUTPUT = ROOT / "evaluation/ai-reference/feedback-decision-1.0.0/sol-pass1.jsonl"

PRODUCTS = (
    "Aurora A17 Graphics Card",
    "Borealis B24 Graphics Card",
    "Cobalt C04 NVMe Drive",
    "Drift D08 SATA Drive",
    "Ember E27 Monitor",
    "Fjord F32 Monitor",
    "Grove G75 Keyboard",
    "Halo H20 Mouse",
    "Juniper J60 Router",
    "Kestrel K12 Processor",
    "Lumen L85 Power Supply",
    "Mica M10 Office Chair",
)


def normalized(text: str) -> str:
    for product in PRODUCTS:
        text = text.replace(product, "<PRODUCT>")
    return re.sub(r"\b\d+\b", "<N>", text)


def answers(
    primary_topic: str,
    mentions_product: bool,
    mentions_delivery: bool,
    mentions_support: bool,
    overall_experience: int,
    product_experience: int = 2,
    delivery_experience: int = 2,
    support_experience: int = 2,
    reports_product_defect: bool = False,
    issue_severity: int = 0,
    resolution_status: str = "not_applicable",
    actionable_feedback: bool = True,
    explicit_repurchase_risk: bool = False,
    defect_type: str = "unclear",
) -> dict[str, dict[str, object]]:
    return {
        "primary_topic": {"type": "choice", "value": primary_topic},
        "mentions_product": {"type": "noul", "value": mentions_product},
        "mentions_delivery": {"type": "noul", "value": mentions_delivery},
        "mentions_support": {"type": "noul", "value": mentions_support},
        "overall_experience": {"type": "score", "value": overall_experience},
        "product_experience": {"type": "score", "value": product_experience},
        "delivery_experience": {"type": "score", "value": delivery_experience},
        "support_experience": {"type": "score", "value": support_experience},
        "reports_product_defect": {"type": "noul", "value": reports_product_defect},
        "issue_severity": {"type": "score", "value": issue_severity},
        "resolution_status": {"type": "choice", "value": resolution_status},
        "actionable_feedback": {"type": "noul", "value": actionable_feedback},
        "explicit_repurchase_risk": {"type": "noul", "value": explicit_repurchase_risk},
        "defect_type": {"type": "choice", "value": defect_type},
    }


def annotate(channel: str, language: str, text: str) -> dict[str, dict[str, object]]:
    del language
    t = normalized(text)

    if channel == "delivery_survey":
        if t in {
            "Clear tracking and an early delivery made this order very easy.",
            "Delivery was quicker than expected and the package was in perfect condition.",
            "Leveransen gick snabbare än väntat och paketet var i perfekt skick.",
            "Tydlig spårning och tidig leverans gjorde beställningen enkel.",
        }:
            return answers("delivery", False, True, False, 4, delivery_experience=4)
        if t in {
            "The product is fine, but delivery was <N> days later than promised.",
            "Produkten är bra men leveransen kom <N> dagar senare än utlovat.",
        }:
            return answers(
                "delivery", True, True, False, 1,
                product_experience=3, delivery_experience=1,
                issue_severity=2, resolution_status="unclear",
            )
        if t in {
            "Tracking did not update and the parcel arrived <N> days late.",
            "Spårningen uppdaterades inte och paketet kom <N> dagar för sent.",
        }:
            return answers(
                "delivery", False, True, False, 1,
                delivery_experience=1, issue_severity=2,
                resolution_status="unclear",
            )

    if channel == "return_feedback":
        if t in {
            "The return label arrived quickly and the refund was completed without trouble.",
            "Returetiketten kom snabbt och återbetalningen gick igenom utan problem.",
        }:
            return answers("returns_refunds", False, False, False, 4, resolution_status="resolved")
        if t in {
            "A replacement was sent as soon as the returned item was scanned.",
            "En ersättningsvara skickades så snart returen registrerades.",
        }:
            return answers("returns_refunds", False, False, False, 3, resolution_status="resolved")
        if t in {
            "The return was received <N> days ago, but the refund is still missing.",
            "Returen togs emot för <N> dagar sedan men återbetalningen saknas fortfarande.",
            "I sent the item back and cannot get a clear update on the return.",
            "Jag skickade tillbaka varan men får inget tydligt besked om returen.",
        }:
            return answers(
                "returns_refunds", False, False, False, 1,
                issue_severity=2, resolution_status="unresolved",
            )

    if channel == "support_ticket":
        if t in {
            "Support explained the checks clearly and solved the issue on the first contact.",
            "Supporten förklarade kontrollerna tydligt och löste problemet direkt.",
        }:
            return answers(
                "support", False, False, True, 4,
                support_experience=4, resolution_status="resolved",
            )
        if t in {
            "The agent arranged a replacement immediately and kept me informed throughout.",
            "Kundtjänsten ordnade en ersättningsprodukt direkt och höll mig uppdaterad.",
        }:
            return answers(
                "support", False, False, True, 4,
                support_experience=4, issue_severity=2,
                resolution_status="resolved",
            )
        if t in {
            "Support repeated the same steps, but the issue remains unresolved.",
            "Supporten upprepade samma steg men problemet är fortfarande olöst.",
        }:
            return answers(
                "support", False, False, True, 1,
                support_experience=1, issue_severity=2,
                resolution_status="unresolved",
            )
        if t == "I have contacted support twice and still do not have an answer or a working product.":
            return answers(
                "support", True, False, True, 0,
                product_experience=0, support_experience=0,
                reports_product_defect=True,
                issue_severity=3, resolution_status="unresolved",
            )
        if t == "Jag har kontaktat supporten två gånger men saknar fortfarande en lösning.":
            return answers(
                "support", False, False, True, 1,
                support_experience=1, issue_severity=2,
                resolution_status="unresolved",
            )

    if channel == "site_feedback":
        if t in {
            "The coffee near the shop was excellent, but I have no product feedback.",
            "Kaffet nära butiken var gott men jag har ingen produktfeedback.",
            "I was browsing during lunch and have not decided what I need yet.",
            "Jag tittade runt på lunchen och har inte bestämt vad jag behöver ännu.",
        }:
            return answers("other", False, False, False, 2, actionable_feedback=False)
        if t in {
            "Checkout lost my basket once, but the second attempt worked.",
            "Kassan tappade min varukorg en gång men det andra försöket fungerade.",
        }:
            return answers(
                "website_checkout", True, False, False, 2,
                issue_severity=1, resolution_status="resolved",
            )
        if t in {
            "The product filters were useful, although payment took too many steps.",
            "Produktfiltren var bra men betalningen krävde för många steg.",
        }:
            return answers(
                "website_checkout", True, False, False, 2,
                issue_severity=1, resolution_status="unclear",
            )
        if t in {
            "The specifications were helpful, but the compatibility section needs more detail.",
        }:
            return answers(
                "product_information", True, False, False, 2,
                issue_severity=1, resolution_status="unresolved",
            )
        if t in {
            "I found the right model, though the dimensions were difficult to locate.",
            "Jag hittade rätt modell men måtten var svåra att hitta.",
        }:
            return answers(
                "product_information", True, False, False, 2,
                issue_severity=1, resolution_status="unclear",
            )

    if channel == "product_review":
        if t in {
            "Really pleased with the <PRODUCT>; performance has been excellent so far.",
            "Mycket nöjd med <PRODUCT>; prestandan har varit riktigt bra hittills.",
        }:
            return answers("product_quality", True, False, False, 4, product_experience=4)
        if t in {
            "The <PRODUCT> works exactly as expected and was easy to set up.",
            "<PRODUCT> fungerar precis som förväntat och var enkel att installera.",
        }:
            return answers("product_quality", True, False, False, 3, product_experience=3)
        if t in {
            "Good value overall and the performance matches more expensive alternatives.",
            "Bra värde för pengarna och prestandan matchar dyrare alternativ.",
        }:
            return answers("price_value", True, False, False, 3, product_experience=3)
        if t in {
            "The <PRODUCT> is solid for the price, although the accessories feel basic.",
            "<PRODUCT> är prisvärd även om tillbehören känns enkla.",
        }:
            return answers(
                "price_value", True, False, False, 3,
                product_experience=3, issue_severity=1,
                resolution_status="unclear",
            )
        if t in {
            "Fine, I suppose. Nothing stands out yet.",
            "Helt okej antar jag. Inget sticker ut än.",
        }:
            return answers(
                "product_quality", True, False, False, 2,
                actionable_feedback=False,
            )
        if t in {
            "The <PRODUCT> is fast and quiet, but the setup guide was confusing and incomplete.",
            "<PRODUCT> är snabb och tyst men installationsguiden var otydlig.",
            "Bra prestanda, but the setup guide made no sense.",
        }:
            return answers(
                "product_information", True, False, False, 3,
                product_experience=3, issue_severity=1,
                resolution_status="unclear",
            )
        if t == "Great speed, men installationen tog hela kvällen.":
            return answers(
                "product_quality", True, False, False, 2,
                product_experience=2, issue_severity=1,
                resolution_status="unclear",
            )
        if t in {
            "Great build quality, yet delivery and initial setup were both frustrating.",
            "Bra byggkvalitet men både leveransen och installationen var frustrerande.",
        }:
            return answers(
                "delivery", True, True, False, 1,
                product_experience=3, delivery_experience=1,
                issue_severity=1, resolution_status="unclear",
            )
        if t in {
            "The <PRODUCT> is probably fine, but it is not compatible with my current setup.",
            "<PRODUCT> verkar bra men är inte kompatibel med min nuvarande dator.",
        }:
            return answers(
                "compatibility", True, False, False, 1,
                product_experience=1, issue_severity=3,
                resolution_status="unresolved",
            )
        if t in {
            "Installation failed because the supplied connector does not fit my system.",
            "Installationen misslyckades eftersom den medföljande kontakten inte passar.",
        }:
            return answers(
                "compatibility", True, False, False, 1,
                product_experience=1, issue_severity=3,
                resolution_status="unresolved",
            )
        if t in {
            "There is a persistent buzzing noise from the <PRODUCT> whenever I start a game.",
            "Det kommer ett konstant surrande ljud från <PRODUCT> när jag startar ett spel.",
        }:
            return answers(
                "product_quality", True, False, False, 1,
                product_experience=1, reports_product_defect=True,
                issue_severity=2, resolution_status="unresolved", defect_type="noise",
            )
        if t in {
            "The <PRODUCT> performs well, but it makes a sharp whining noise under load.",
            "<PRODUCT> presterar bra men ger ifrån sig ett tydligt vinande ljud under belastning.",
        }:
            return answers(
                "product_quality", True, False, False, 2,
                product_experience=2, reports_product_defect=True,
                issue_severity=1, resolution_status="unresolved", defect_type="noise",
            )
        if t in {
            "The finish looked damaged when the <PRODUCT> arrived and one part was loose.",
            "<PRODUCT> var skadad vid leverans och en del satt löst.",
        }:
            return answers(
                "product_quality", True, True, False, 1,
                product_experience=1, delivery_experience=1,
                reports_product_defect=True, issue_severity=2,
                resolution_status="unresolved", defect_type="physical_damage",
            )
        if t == "The <PRODUCT> arrived damged and now it wont start at all.":
            return answers(
                "product_quality", True, True, False, 0,
                product_experience=0, delivery_experience=1,
                reports_product_defect=True, issue_severity=3,
                resolution_status="unresolved", defect_type="physical_damage",
            )
        if t == "Kom trasig. Funkar inte alls.":
            return answers(
                "product_quality", True, True, False, 0,
                product_experience=0, delivery_experience=1,
                reports_product_defect=True, issue_severity=3,
                resolution_status="unresolved", defect_type="other",
            )
        if t in {
            "The <PRODUCT> stopped working after a week and now disconnects at random.",
            "<PRODUCT> slutade fungera efter en vecka och kopplar nu ner slumpmässigt.",
        }:
            return answers(
                "product_quality", True, False, False, 0,
                product_experience=0, reports_product_defect=True,
                issue_severity=3, resolution_status="unresolved", defect_type="stability",
            )
        if t == "Perfect, another restart just when I needed it most.":
            return answers(
                "product_quality", True, False, False, 0,
                product_experience=0, reports_product_defect=True,
                issue_severity=2, resolution_status="unresolved", defect_type="stability",
            )

    raise ValueError(f"unclassified record: {channel=} {t=}")


def main() -> None:
    rows = []
    with RECORDS.open() as source:
        for line in source:
            record = json.loads(line)
            rows.append({
                "feedback_id": record["feedback_id"],
                "pass": 1,
                "annotator_id": "sol-medium-pass-1",
                "answers": annotate(record["channel"], record["language"], record["feedback_text"]),
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w") as destination:
        for row in rows:
            destination.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
