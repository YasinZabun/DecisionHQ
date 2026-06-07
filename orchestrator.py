import asyncio
import json
import yaml
from pypdf import PdfReader
from llm_client import LLMClientFactory, encode_image_to_base64
import personas

class DecisionHQOrchestrator:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.max_rounds = self.config["system_settings"]["max_debate_rounds"]
        
        # İstemcileri Hazırla
        self.chair = LLMClientFactory.create_client(
            self.config["moderator"]["provider"],
            self.config["moderator"]["deployment_name"],
            self.config["moderator"]["temperature"]
        )
        
        self.agents = {}
        for agent_name, settings in self.config["agents"].items():
            self.agents[agent_name] = {
                "client": LLMClientFactory.create_client(
                    settings["provider"], settings["deployment_name"], settings["temperature"]
                ),
                "prompt": getattr(personas, f"{agent_name.upper()}_PROMPT"),
                "history": []
            }

    async def run_pipeline(self, raw_text: str, pdf_path: str = None, image_path: str = None, on_event=None):

        async def emit(event_type: str, **data):
            if on_event:
                await on_event(event_type, data)

        print("[⚡] Aşama 1: Veri Odası Toplanıyor ve Multimodal Girdiler İşleniyor...")
        await emit("stage", message="Girdiler işleniyor...", stage="init")
        
        combined_content = [{"type": "text", "text": f"Kullanıcı Temel Girdisi:\n{raw_text}"}]
        
        if pdf_path:
            reader = PdfReader(pdf_path)
            pdf_text = "".join([page.extract_text() for page in reader.pages])
            combined_content.append({"type": "text", "text": f"\nEkteki PDF Doküman İçeriği:\n{pdf_text}"})
            print(f"[📄] PDF okundu: {pdf_path}")
            
        if image_path:
            base64_image = encode_image_to_base64(image_path)
            combined_content.append({
                "type": "image_url",
                "image_url": {"url": base64_image}
            })
            print(f"[📸] Görsel yüklendi ve entegre edildi: {image_path}")

        # --- AŞAMA 2: EGO CHECK ---
        print("\n[🧠] Aşama 2: Başkan (The Chair) Ego-Check Analizini Başlatıyor...")
        await emit("stage", message="Başkan Ego-Check analizi yapıyor...", stage="ego_check")
        ego_check_messages = [
            {"role": "system", "content": personas.CHAIR_SYSTEM_PROMPT},
            {"role": "user", "content": combined_content + [{"type": "text", "text": "Kullanıcının bu girdisini dürüstçe analiz et. Şunları tespit et: (1) Gerçek sorusunun arkasındaki asıl korku ya da motivasyon nedir? (2) Zaten almış olduğu kararı onaylatmaya mı çalışıyor? (3) Hangi bilgileri seçici olarak paylaşmış ya da atlamış? (4) Bu kararın ardındaki kimlik çatışması, ego baskısı veya saptırma mekanizması nedir? Bu analizi yalnızca nihai sentez raporunu yazmak için kullan — konsey üyelerine yönlendirme olarak iletme."}]}


        ]
        ego_directive = await self.chair.generate_response(ego_check_messages)
        print("-> Ego-Check Tamamlandı. Direktif yalnızca Başkan'ın nihai sentezi için saklandı.")
        await emit("ego_check_complete", directive=ego_directive)

        # --- AŞAMA 3: MÜNAZARA DÖNGÜSÜ ---
        debate_transcript = ""
        agent_names = list(self.agents.keys())
        
        for r in range(1, self.max_rounds + 1):
            print(f"\n[⚔️] Aşama 3: Münazara Döngüsü - Tur {r} / {self.max_rounds}")
            await emit("debate_round_start", round=r, total=self.max_rounds)
            tasks = []
            
            for name in agent_names:
                agent = self.agents[name]
                messages = [{"role": "system", "content": agent["prompt"]}]
                
                if r == 1:
                    # İlk turda yalnızca ham girdiler — ego direktifi ajanlara iletilmiyor
                    user_payload = combined_content + [
                        {"type": "text", "text": "\nLütfen kendi personan ekseninde açılış pozisyonunu (Opening Position) yaz."}
                    ]
                    messages.append({"role": "user", "content": user_payload})
                else:
                    # Sonraki turlarda ajanın geçmişi (içinde sadece ona sorulan soru var) iletilir
                    messages.extend(agent["history"])
                    
                tasks.append(agent["client"].generate_response(messages))
                
            responses = await asyncio.gather(*tasks)
            
            # Bu turun çıktılarını kaydet ve logla
            round_transcript = f"\n--- TUR {r} TARTIŞMA KAYITLARI ---\n"
            for name, response in zip(agent_names, responses):
                print(f"   [{name.upper()}] yanıtını verdi.")
                self.agents[name]["history"].append({"role": "assistant", "content": response})
                round_transcript += f"[{name.upper()}]:\n{response}\n\n"
                await emit("agent_response", agent=name, response=response)
                
            debate_transcript += round_transcript
            
            # Eğer son turda değilsek, başkan her ajana ÖZEL VE AYRI sorusunu hazırlar
            if r < self.max_rounds:
                print(f"[📢] Başkan (The Chair) Tur {r} çıktılarını inceliyor ve Nokta Atışı İtirazları Hazırlıyor...")
                
                chair_json_schema = """
                Münazara tutanaklarını oku. Her üyenin argümanındaki en büyük açığı, çelişkiyi veya kanıtlanmamış varsayımı tespit et.
                Her bir üyeye YALNIZCA ONUN argümanını köşeye sıkıştıracak, somut ve spesifik bir Sokratik soru hazırla.
                Kurallar: (1) Genel soru değil, o üyenin söylediği spesifik bir iddiayı sorgula. (2) Yumuşak olma — üyeyi gerçekten zora sokacak soruyu sor. (3) The Philosopher için: öne sürdüğü yeniden çerçevelemenin kendisini sorgula.
                Çıktıyı kesinlikle şu JSON formatında ver:
                {
                  "macro_predictor": "Bu ajana özel Sokratik soru",
                  "wealth_alchemist": "Bu ajana özel Sokratik soru",
                  "grit_craft": "Bu ajana özel Sokratik soru",
                  "the_hacker": "Bu ajana özel Sokratik soru",
                  "the_executioner": "Bu ajana özel Sokratik soru",
                  "the_cynic": "Bu ajana özel Sokratik soru",
                  "legal_ethics_guard": "Bu ajana özel Sokratik soru",
                  "human_factor": "Bu ajana özel Sokratik soru",
                  "the_realist": "Bu ajana özel Sokratik soru",
                  "the_philosopher": "Bu ajana özel Sokratik soru"
                }
                """
                
                chair_messages = [
                    {"role": "system", "content": personas.CHAIR_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Şu ana kadar yapılan tartışma tutanakları aşağıdadır:\n{round_transcript}\n\n{chair_json_schema}"}
                ]
                
                # Başkanın yapılandırılmış JSON yanıtını alıyoruz
                chair_challenges_raw = await self.chair.generate_response(chair_messages, json_mode=True)
                chair_challenges = json.loads(chair_challenges_raw)
                
                # [ÇÖZÜM]: Her ajanın geçmişine YALNIZCA KENDİNE ait soruyu ekliyoruz
                for name in agent_names:
                    specific_question = chair_challenges.get(name, "Lütfen önceki argümanını derinleştir ve savun.")
                    
                    self.agents[name]["history"].append({
                        "role": "user",
                        "content": f"Moderatörün SADECE SANA yönelik Sokratik meydan okuması:\n{specific_question}\n\nBu eleştiriye personana sadık kalarak, spesifik ve somut bir şekilde cevap ver. Muğlak kalmak yasaktır. Argümanını ya savun (kanıt ve rakamlarla) ya da revize et — ama ikisini de net yap."
                    })
                print("-> Başkanın nokta atışı soruları gizlilik ihlali olmadan ajanların hafızalarına işlendi.")
                await emit("chair_challenges", round=r, challenges=chair_challenges)

        # --- AŞAMA 4: NİHAİ SENTEZ VE RAPORLAMA ---
        print("\n[🏆] Aşama 4: Münazara Bitti. Başkan Nihai Sentez Raporunu Hazırlıyor (JSON Mode)...")
        await emit("synthesis_start")
        
        schema_instruction = """
        Bütün tartışma geçmişini ve girdileri sentezleyerek aşağıdaki JSON formatında çıktı üret.

        ÖNEMLİ — `report` alanı için talimat:
        Bu alanı yazmadan önce şu soruları sor:
          1. Bu ne tür bir soru? (Kişisel karar / İlişkisel / Finansal / Kariyer / Sağlık / Varoluşsal / Stratejik)
          2. Kullanıcının gerçekten neye ihtiyacı var? (Netlik mi? Eylem planı mı? Duygusal dürüstlük mü? Alternatif perspektif mi?)
          3. Hangi yazı formatı bu soruya en çok hizmet eder?

        Format örnekleri (bunlarla sınırlı değil, yeni format da icat edebilirsin):
          - Varoluşsal / kimlik sorusu → Felsefi bir çerçeve + yaşamsal dürüstlük + pratik yönlendirme
          - İlişki / aile kararı → Empatiyle açılan ama gerçekçi biten bir mektup tarzı
          - Kariyer / stratejik karar → Sert hüküm + net karşılaştırma + öncelikli adımlar
          - Finansal karar → Sayısal anatomi + risk profili + karar ağacı
          - Sağlık / yaşam tarzı → Biyolojik gerçekçilik + sürdürülebilirlik + somut protokol
          - Karma / belirsiz → Önce soruyu yeniden çerçevele, sonra her boyutu ayrı ele al

        `report` yazdıktan SONRA `chosen_format`'ı doldur: neden o formatı seçtiğini bir cümleyle açıkla.

        {
          "question_type": "Sorunun birincil türü",

          "ego_check_analysis": "Kullanıcının gerçek motivasyonu, gizli korkusu, onay arayışı ve kaçınma mekanizmaları — münazaradan bağımsız, yalnızca ilk girdi analizine dayalı, spesifik ve dürüst.",

          "consensus_status": "Full Consensus | Split Decision | Deep Divide — kimin nerede ayrıştığı ve bu ayrışmanın önemi.",

          "member_arguments": {
            "macro_predictor": "Baskın makro güç ve tarihsel örüntünün argüman biçiminde özeti. Uzun vadeli projeksiyon.",
            "wealth_alchemist": "Finansal anatomi: gerçek maliyet, fırsat maliyeti, tahmini getiri. Mümkün olduğunca rakam ver.",
            "grit_craft": "Bu hedef için gerçekte gereken emek ve kullanıcının mevcut konumu arasındaki uçurumun dürüst özeti.",
            "the_hacker": "Önerilen kaldıraç noktaları veya spesifik taktikler ve gerekçesi.",
            "the_executioner": "İlk somut adımlar ve 30 günlük hedef. Kaynaklar ve öngörülen engeller.",
            "the_cynic": "Temel başarısızlık senaryosu ve konseyin görmezden geldiği en kritik değişken.",
            "legal_ethics_guard": "Tespit edilen yasal, etik veya itibarsal risk ve kırmızı çizgiler.",
            "human_factor": "Psikolojik sürdürülebilirlik değerlendirmesi ve insani bedelin özeti.",
            "the_realist": "Bu soruyla ilgili somut yapısal gerçeklikler: piyasa durumu, kurumsal engeller, jeopolitik bağlam — sadece ilgili olanlar.",
            "the_philosopher": "Sorunun yeniden çerçevelenmesi ve tespit edilen gizli varsayım veya yanlış ikilem."
          },

          "chosen_format": "Bu raporun formatını neden seçtim — bir cümle.",

          "metrics": {
            "overall_risk_score": "<Bu kararın genel risk skoru, 1-10 tam sayı — 10 kritik risk>",
            "implementation_difficulty": "<Uygulamanın zorluğu, 1-10 tam sayı>",
            "time_to_first_result_weeks": "<İlk somut sonuç için gereken hafta sayısı, tam sayı>",
            "consensus_strength": "<Konsey uzlaşısının gücü, 1-10 tam sayı — 10 tam mutabakat>",
            "burnout_risk_score": "<İnsani tükenmişlik riski, 1-10 tam sayı>",
            "financial_exposure_score": "<Finansal maruziyet, 1-10 tam sayı>"
          },

          "report": "SERBEST FORMAT — yukarıdaki analize dayanarak, bu soruya en uygun yapıda yazılmış kullanıcıya yönelik tam rapor. Doğrudan 'sen' diye hitap et. Teknik jargon değil, anlaşılır ve güçlü bir dil kullan. Şablona hapsolma. Minimum 400 kelime."
        }
        """
        
        final_messages = [
            {"role": "system", "content": personas.CHAIR_SYSTEM_PROMPT},
            {"role": "user", "content": f"Tüm Girdiler:\n{raw_text}\n\nTüm Münazara Geçmişi:\n{debate_transcript}\n\nEgo Check Analizin:\n{ego_directive}\n\n{schema_instruction}"}
        ]
        
        final_json_output = await self.chair.generate_response(final_messages, json_mode=True)
        return json.loads(final_json_output)