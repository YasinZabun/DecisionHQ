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

    async def run_pipeline(self, raw_text: str, pdf_path: str = None, image_path: str = None):
        print("[⚡] Aşama 1: Veri Odası Toplanıyor ve Multimodal Girdiler İşleniyor...")
        
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
        ego_check_messages = [
            {"role": "system", "content": personas.CHAIR_SYSTEM_PROMPT},
            {"role": "user", "content": combined_content + [{"type": "text", "text": "Kullanıcının bu girdisini analiz et. Gizli korkularını, onaylanma beklentilerini ve konfor alanı zaaflarını saptayıp konsey üyelerine hitaben gizli bir direktif yaz."}]}
        ]
        ego_directive = await self.chair.generate_response(ego_check_messages)
        print("-> Ego-Check Tamamlandı. Konsey üyelerine stratejik direktif fonlandı.")

        # --- AŞAMA 3: MÜNAZARA DÖNGÜSÜ ---
        debate_transcript = ""
        agent_names = list(self.agents.keys())
        
        for r in range(1, self.max_rounds + 1):
            print(f"\n[⚔️] Aşama 3: Münazara Döngüsü - Tur {r} / {self.max_rounds}")
            tasks = []
            
            for name in agent_names:
                agent = self.agents[name]
                messages = [{"role": "system", "content": agent["prompt"]}]
                
                if r == 1:
                    # İlk turda ham girdiler ve ego direktifi gönderilir
                    user_payload = combined_content + [
                        {"type": "text", "text": f"\nModeratörden Gelen Stratejik Gizli Direktif:\n{ego_directive}\n\nLütfen kendi personan ekseninde açılış pozisyonunu (Opening Position) yaz."}
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
                
            debate_transcript += round_transcript
            
            # Eğer son turda değilsek, başkan her ajana ÖZEL VE AYRI sorusunu hazırlar
            if r < self.max_rounds:
                print(f"[📢] Başkan (The Chair) Tur {r} çıktılarını inceliyor ve Nokta Atışı İtirazları Hazırlıyor...")
                
                chair_json_schema = """
                Münazara tutanaklarını oku. Üyelerin arasındaki çelişkileri yakala.
                Her bir üyeye (macro_predictor, wealth_alchemist, grit_craft, the_hacker, the_executioner, the_cynic, legal_ethics_guard, human_factor), sadece onun argümanını çökertecek, onu köşeye sıkıştıracak ÖZEL BİRER soru hazırla.
                Çıktıyı kesinlikle şu JSON formatında ver:
                {
                  "macro_predictor": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "wealth_alchemist": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "grit_craft": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "the_hacker": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "the_executioner": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "the_cynic": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "legal_ethics_guard": "Sadece bu ajana sorulacak Sokratik soru metni",
                  "human_factor": "Sadece bu ajana sorulacak Sokratik soru metni"
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
                        "content": f"Moderatörün SADECE SANA yönelik Sokratik meydan okuması:\n{specific_question}\n\nBu eleştiriye personana sadık kalarak ve sadece kendi alanından cevap ver."
                    })
                print("-> Başkanın nokta atışı soruları gizlilik ihlali olmadan ajanların hafızalarına işlendi.")

        # --- AŞAMA 4: NİHAİ SENTEZ VE RAPORLAMA ---
        print("\n[🏆] Aşama 4: Münazara Bitti. Başkan Nihai Sentez Raporunu Hazırlıyor (JSON Mode)...")
        
        schema_instruction = """
        Bütün tartışma geçmişini ve girdileri sentezleyerek şu JSON formatına kesinlikle uyacak bir çıktı üret:
        {
          "ego_check_analysis": "Kullanıcının psikolojik zaaf ve onaylanma beklentisi analizi.",
          "consensus_status": "Full Consensus veya Split Decision",
          "member_arguments": {
             "macro_predictor": "Son duruş özeti",
             "wealth_alchemist": "Son duruş özeti",
             "grit_craft": "Son duruş özeti",
             "the_hacker": "Son duruş özeti",
             "the_executioner": "Son duruş özeti — pazartesi sabahı 09:00'da atılacak ilk somut adım dahil",
             "the_cynic": "Son duruş özeti — en kritik başarısızlık senaryosu ve gözden kaçan değişkenler",
             "legal_ethics_guard": "Son duruş özeti — tespit edilen yasal/regülatif/etik riskler",
             "human_factor": "Son duruş özeti — kullanıcının mental ve fiziksel sürdürülebilirlik analizi"
          },
          "risk_clusters": "Finansal, teknik, sosyolojik, operasyonel, yasal ve insani risklerin gruplanmış analizi.",
          "first_move": "The Executioner'ın netleştirdiği, yarın uygulamaya girilebilecek en küçük ve en somut ilk adım.",
          "worst_case_scenario": "The Cynic'in öngördüğü en gerçekçi felaket senaryosu ve bu senaryoya karşı alınabilecek önlemler.",
          "legal_guardrails": "Legal & Ethics Guard'ın belirlediği kesin sınırlar ve uyulması zorunlu kurallar.",
          "human_sustainability_check": "Human Factor'ın insani sürdürülebilirlik skoru ve önerilen enerji yönetimi stratejisi.",
          "action_plan": "Kısa vadeli hacker taktikleri ile uzun vadeli derin emeği birleştiren, operasyonel olarak uygulanabilir, yasal sınırlar içinde kalan ve insani kapasiteye saygılı melez çok detaylı yol gösterici eylem planı."
        }
        """
        
        final_messages = [
            {"role": "system", "content": personas.CHAIR_SYSTEM_PROMPT},
            {"role": "user", "content": f"Tüm Girdiler:\n{raw_text}\n\nTüm Münazara Geçmişi:\n{debate_transcript}\n\nEgo Check Analizin:\n{ego_directive}\n\n{schema_instruction}"}
        ]
        
        final_json_output = await self.chair.generate_response(final_messages, json_mode=True)
        return json.loads(final_json_output)