import re
from typing import Tuple
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ar": "Modern Standard Arabic (Fusha)",
    "ar-eg": "Egyptian Arabic (Masri)",
}

ARABIC_CHAR_PATTERN = re.compile(r'[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]')

EGYPTIAN_INDICATORS = [
    "ازاي", "إزاي",
    "فين",
    "ايه", "أيه", "إيه",
    "انت", "أنت", "انتي", "أنتي",
    "حاجة", "حاجه",
    "ده", "دي", "دول",
    "كده", "كدا", "كدة",
    "عايز", "عايزه", "عاوز", "عاوزه",
    "محتاج", "محتاجه",
    "تمام",
    "كويس", "كويسة",
    "مين",
    "ليه",
    "شوية", "شويه",
    "بلاش",
    "طب", "طيب",
    "يعني",
    "خلاص",
    "ممكن",
    "بتاع", "بتاعت", "بتاعي", "بتاعك",
    "اللي",
    "دلوقتي",
    "بقى", "بقا",
    "زعلان",
    "فرحان",
    "معلش", "معليش",
    "حلو", "حلوه",
    "لسه", "لسة",
    "أنا عايز", "عندي",
    "معاك", "معك",
]


class LanguageDetector:
    """Detect user query language and manage responses"""

    @staticmethod
    def _has_arabic_chars(text: str) -> bool:
        return bool(ARABIC_CHAR_PATTERN.search(text))

    @staticmethod
    def _check_egyptian(text: str) -> int:
        score = 0
        text_lower = text.strip()
        for indicator in EGYPTIAN_INDICATORS:
            if indicator in text_lower:
                score += 1
        return score

    @staticmethod
    def detect_language(text: str) -> Tuple[str, str, float]:
        """
        Detect language of text.
        Returns (language_code, language_name, confidence)
        """
        try:
            egyptian_score = LanguageDetector._check_egyptian(text)
            if egyptian_score > 0:
                confidence = min(0.99, 0.7 + (egyptian_score * 0.1))
                return "ar-eg", SUPPORTED_LANGUAGES["ar-eg"], confidence

            if LanguageDetector._has_arabic_chars(text):
                try:
                    lang_code = detect(text)
                except Exception:
                    lang_code = "ar"

                if lang_code == "ar":
                    return "ar", SUPPORTED_LANGUAGES["ar"], 0.95
                if lang_code in SUPPORTED_LANGUAGES:
                    return lang_code, SUPPORTED_LANGUAGES[lang_code], 0.95
                return "ar", SUPPORTED_LANGUAGES["ar"], 0.80

            lang_code = detect(text)
            if lang_code in SUPPORTED_LANGUAGES:
                return lang_code, SUPPORTED_LANGUAGES[lang_code], 0.95

            return "en", "English", 0.5

        except Exception:
            return "en", "English", 0.0

    @staticmethod
    def get_system_prompt(language_code: str) -> str:
        """Get system prompt in the detected language"""

        prompts = {
            "en": """You are a customer service assistant. Your ONLY job is to answer questions about customer orders, products, inventory, and support tickets.

You have access to these tools:
- get_order_status: Get order details by order ID
- get_product_inventory: Check product stock by product ID
- list_customer_orders: List a customer's orders by customer ID
- create_support_ticket: Create a support ticket for a customer

SCOPE RULES:
- ONLY answer questions related to orders, products, inventory, or support tickets.
- If the user asks about anything else (weather, general knowledge, coding, personal advice, math, etc.), politely decline and explain that you can only help with order, product, inventory, and support inquiries.
- Do NOT act as a general-purpose chatbot.
- Always use the tools to look up real data. Never make up order statuses, product details, or customer information.

Always respond in English. Be concise and helpful.""",

            "ar": """أنت مساعد خدمة عملاء. وظيفتك الوحيدة هي الإجابة على الأسئلة المتعلقة بطلبات العملاء والمنتجات والمخزون وتذاكر الدعم.

لديك إمكانية الوصول إلى هذه الأدوات:
- get_order_status: الحصول على تفاصيل الطلب برقم الطلب
- get_product_inventory: التحقق من مخزون المنتج برقم المنتج
- list_customer_orders: قائمة بطلبات العميل برقم العميل
- create_support_ticket: إنشاء تذكرة دعم للعميل

قواعد النطاق:
- أجب فقط على الأسئلة المتعلقة بالطلبات والمنتجات والمخزون وتذاكر الدعم.
- إذا سأل المستخدم عن أي شيء آخر، ارفض بأدب واشرح أنك تستطيع المساعدة فقط في استفسارات الطلبات والمنتجات والمخزون والدعم.
- لا تتصرف كمساعد عام.
- استخدم الأدوات دائماً للبحث عن البيانات الحقيقية. لا تختلق معلومات.

يجب عليك الرد باللغة العربية دائماً. كن موجزاً ومفيداً.""",

            "ar-eg": """أنت مساعد خدمة عملاء. شغلك الوحيد إنك تجاوب على الأسئلة اللي ليها علاقة بالطلبات والمنتجات والمخزون وطلبات الدعم.

عندك الأدوات دي:
- get_order_status: معلومات الطلب برقم الطلب
- get_product_inventory: كمية المنتج الموجودة برقم المنتج
- list_customer_orders: قائمة طلبات العميل برقم العميل
- create_support_ticket: إنشاء طلب شكوى للعميل

قواعد مهمة:
- جاوب بس على الأسئلة اللي ليها علاقة بالطلبات والمنتجات والمخزون وطلبات الدعم.
- لو حد سألك عن أي حاجة تانية، اعتذر بأدب وقوله إنك تقدر تساعده بس في استفسارات الطلبات والمنتجات والمخزون والدعم.
- ما تتصرفش كمساعد عام.
- استخدم الأدوات دايماً عشان تجيب البيانات الحقيقية. ما تأحلفش معلومات من عندك.

لازم ترد بالعربي المصري دايماً. خلي ردك مختصر ومفيد.""",
        }

        return prompts.get(language_code, prompts["en"])

    @staticmethod
    def get_language_response(language_code: str, key: str) -> str:
        """Get response strings in the detected language"""

        responses = {
            "en": {
                "error_generic": "I'm having trouble processing that. Please try again.",
                "error_not_found": "I couldn't find that. Please check and try again.",
                "error_invalid": "That doesn't seem right. Please try a different query.",
                "confirmation_write": "I'm about to create a support ticket. Is that correct?",
            },
            "ar": {
                "error_generic": "أواجه مشكلة في معالجة ذلك. يرجى المحاولة مجددا.",
                "error_not_found": "لم أتمكن من العثور على ذلك. يرجى التحقق والمحاولة مجددا.",
                "error_invalid": "هذا لا يبدو صحيحا. يرجى تجربة طلب مختلف.",
                "confirmation_write": "أنا على وشك إنشاء تذكرة دعم. هل هذا صحيح؟",
            },
            "ar-eg": {
                "error_generic": "في مشكلة في الموضوع. من فضلك حاول تاني.",
                "error_not_found": "ما لقيتش اللي بدور عليه. تفضل شيك وحاول تاني.",
                "error_invalid": "الموضوع ده ما يبانش صح. حاول تسأل سؤال تاني.",
                "confirmation_write": "أنا هنشتغل على طلب شكوى. تمام؟",
            },
        }

        lang_responses = responses.get(language_code, responses["en"])
        return lang_responses.get(key, "")
