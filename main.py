import asyncio
import argparse
import json
from orchestrator import DecisionHQOrchestrator

def print_report(data: dict):
    width = 70
    print("\n" + "=" * width)
    print("          KARAR KARARGAHI — NİHAİ RAPOR")
    print("=" * width)

    question_type = data.get("question_type", "")
    consensus = data.get("consensus_status", "")
    ego = data.get("ego_check_analysis", "")
    chosen_format = data.get("chosen_format", "")

    if question_type:
        print(f"\n  Konu Türü   : {question_type}")
    if consensus:
        print(f"  Uzlaşı      : {consensus}")
    if chosen_format:
        print(f"  Rapor Biçimi: {chosen_format}")
    if ego:
        print(f"\n  Ego-Check   : {ego}")

    member_args = data.get("member_arguments", {})
    if member_args:
        print("\n" + "-" * width)
        print("  KONSEY KAYITLARI")
        print("-" * width)
        for member, arg in member_args.items():
            label = member.replace("_", " ").upper()
            print(f"\n  [{label}]\n  {arg}")

    report = data.get("report", "")
    if report:
        print("\n" + "=" * width)
        print("  KARAR KARARGAHI RAPORU")
        print("=" * width + "\n")
        print(report)

    print("\n" + "=" * width)

async def main():
    parser = argparse.ArgumentParser(description="Universal Decision Headquarters (Decision HQ) CLI")
    parser.add_argument("--text", type=str, required=True, help="Karar verilmesini istediğiniz konunun özeti veya ham metni")
    parser.add_argument("--pdf", type=str, default=None, help="Konuyla ilgili destekleyici PDF döküman yolu")
    parser.add_argument("--image", type=str, default=None, help="Konuyla ilgili şema, ekran görüntüsü veya görsel yolu")

    args = parser.parse_args()

    orchestrator = DecisionHQOrchestrator(config_path="config.yaml")

    try:
        result = await orchestrator.run_pipeline(
            raw_text=args.text,
            pdf_path=args.pdf,
            image_path=args.image
        )

        print_report(result)

        with open("last_decision_report.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)

    except Exception as e:
        print(f"\n[❌] Karargah işletim hatası: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
