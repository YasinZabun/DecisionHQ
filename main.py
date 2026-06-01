import asyncio
import argparse
import json
from orchestrator import DecisionHQOrchestrator

def print_markdown_report(data: dict):
    """Gelen JSON verisini terminalde harika gözüken bir rapora dönüştürür."""
    print("\n" + "="*60)
    print("      KARAR KARARGAHI (DECISION HQ) NİHAİ STRATEJİ RAPORU      ")
    print("="*60)
    
    print(f"\n## 🧠 1. EGO-CHECK ANALİZİ (GİZLİ EĞİLİMLER)")
    print(f"> {data.get('ego_check_analysis')}")
    
    print(f"\n## 📊 2. KONSEY UZLAŞI DURUMU")
    print(f"**Durum:** {data.get('consensus_status')}")
    
    print(f"\n## 👥 3. KONSEY ÜYELERİNİN SON DURUŞLARI")
    for member, arg in data.get('member_arguments', {}).items():
        print(f"* **{member.upper()}:** {arg}")
        
    print(f"\n## ⚠️ 4. RİSK KÜMELERİ (RISK CLUSTERS)")
    print(data.get('risk_clusters'))
    
    print(f"\n## 🚀 5. AKIL, MANTIK VE FIRSATIN ORTAK YOL HARİTASI (ACTION PLAN)")
    print(data.get('action_plan'))
    print("\n" + "="*60)

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
        
        # Markdown Çıktı
        print_markdown_report(result)
        
        # İleride loglamak istersen diye JSON yedeği
        with open("last_decision_report.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
            
    except Exception as e:
        print(f"\n[❌] Karargah işletim hatası: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())