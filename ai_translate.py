"""
ترجمة سياقية عالية الجودة لملفات POEditor باستخدام Claude API.

الوظيفة:
    - يقرأ ملف CSV مُصدَّراً من POEditor (بصيغة: key, translation, ..., source).
    - يكتشف الصفوف غير المترجمة (عمود الترجمة فارغ والنص المصدر موجود).
    - يترجمها إلى العربية الفصحى حسب السياق باستخدام Claude، مع الحفاظ على:
        * المتغيّرات مثل {current} و {total}
        * وسوم HTML مثل <strong> و <br/>
        * أسطر \\n الجديدة
        * أسماء العلامات التجارية (Tuta، Gmail، IMAP ...)
    - يتخطّى النصوص المُعلَّمة "do not translate" في حقل السياق.
    - يحفظ تقدّمه في ملف كاش (يمكن استئناف العمل بعد أي انقطاع).
    - يُصدّر ملف CSV جديداً بالصيغة نفسها (ترميز utf-8-sig).

المفتاح لا يوجد داخل الكود إطلاقاً — يُقرأ من متغيّر البيئة ANTHROPIC_API_KEY.

طريقة التشغيل:
    export ANTHROPIC_API_KEY="sk-ant-..."
    pip install anthropic pydantic
    python ai_translate.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from typing import Dict, List

import anthropic
from pydantic import BaseModel

# ------------------------------------------------------------------
# الإعدادات
# ------------------------------------------------------------------
INPUT_CSV = "Tuta_Client_Arabic.csv"          # ملف POEditor المصدر
OUTPUT_CSV = "Tuta_Client_Arabic_AI_Translated.csv"  # الملف الناتج
CACHE_FILE = ".translation_cache.json"        # كاش لاستئناف العمل

MODEL = "claude-opus-4-8"   # أحدث نموذج Opus وأكثرها قدرة
BATCH_SIZE = 20             # عدد النصوص في كل طلب (أصغر = أدق، أكبر = أسرع)
OVERWRITE_EXISTING = False  # True لإعادة ترجمة كل شيء حتى المترجَم مسبقاً

TARGET_LANGUAGE = "Arabic (Modern Standard Arabic / العربية الفصحى)"

# مؤشرات الأعمدة في ملف POEditor
KEY_COL = 0        # المفتاح (term)
TRANSLATION_COL = 1  # الترجمة
CONTEXT_COL = 4    # حقل السياق/الملاحظة (قد لا يوجد في كل الصفوف)
# عمود المصدر (الإنجليزي) هو آخر عمود — يُحسب من عرض أول صف.

# مصطلحات موحّدة تُمرَّر للنموذج للحفاظ على اتساق الترجمة عبر الملف كله.
GLOSSARY = {
    "Calendar": "التقويم",
    "Email / Mail": "البريد / رسالة",
    "Settings": "الإعدادات",
    "Password": "كلمة المرور",
    "Plan": "خطة",
    "Subscription": "اشتراك",
    "Folder": "مجلد",
    "Label": "تسمية",
    "Recovery code": "كود الاسترجاع",
    "Mailbox": "صندوق البريد",
    "Contact / Contacts": "جهة اتصال / جهات الاتصال",
    "Spam": "الرسائل المزعجة",
    "Migration": "الترحيل",
}


# ------------------------------------------------------------------
# نماذج المخرجات المنظّمة (Structured Outputs)
# ------------------------------------------------------------------
class TranslatedItem(BaseModel):
    key: str
    translation: str


class TranslationBatch(BaseModel):
    items: List[TranslatedItem]


# ------------------------------------------------------------------
# قراءة / كتابة CSV
# ------------------------------------------------------------------
def read_csv_any_encoding(path: str) -> List[List[str]]:
    for enc in ("utf-8-sig", "utf-8", "windows-1256"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return list(csv.reader(f))
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"تعذّر قراءة الملف: {path}")


def write_csv(path: str, rows: List[List[str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


# ------------------------------------------------------------------
# أدوات التحقق (المتغيّرات ووسوم HTML)
# ------------------------------------------------------------------
def placeholders(text: str) -> List[str]:
    return sorted(re.findall(r"\{[^}]*\}", text))


def html_tags(text: str) -> List[str]:
    return sorted(re.findall(r"</?[a-zA-Z][^>]*>", text))


def is_do_not_translate(context: str) -> bool:
    c = context.lower()
    return "do not translate" in c or "don't translate" in c or "deprecated" in c


# ------------------------------------------------------------------
# الكاش
# ------------------------------------------------------------------
def load_cache() -> Dict[str, str]:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: Dict[str, str]) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


# ------------------------------------------------------------------
# الترجمة عبر Claude
# ------------------------------------------------------------------
SYSTEM_PROMPT = f"""You are an expert software localizer translating UI strings for the Tuta \
(encrypted email & calendar) application into {TARGET_LANGUAGE}.

Rules — follow ALL of them exactly:
1. Translate naturally and contextually, not word-for-word. Use the provided \
"context" note (when present) to disambiguate meaning and tone. Produce fluent, \
professional Modern Standard Arabic that reads well to a native speaker.
2. Preserve EVERY placeholder such as {{current}}, {{total}}, {{mailAddress}} EXACTLY \
as written — same spelling, same braces. Do not translate, reorder inside the braces, \
or add/remove any placeholder.
3. Preserve ALL HTML tags exactly (e.g. <strong>, </strong>, <b>, <br/>, <br>). You may \
move a tag so the sentence reads correctly, but never rename, drop, or add tags.
4. Preserve literal newline characters (\\n) where they appear in the source.
5. Keep brand and technical names in Latin script: Tuta, Tuta Mail, Tuta Calendar, \
App Store, Google Play, Gmail, Outlook, IMAP, PDF, QR, 2FA, plan names like \
Revolutionary and Legend, etc.
6. Return ONLY the translation text for each item — no quotes, no extra commentary.

Use this glossary for consistent terminology:
{json.dumps(GLOSSARY, ensure_ascii=False, indent=2)}
"""


def translate_batch(client: anthropic.Anthropic, batch: List[dict]) -> Dict[str, str]:
    """يترجم دفعة. batch = [{"key","source","context"}, ...] → {key: arabic}."""
    payload = [
        {"key": it["key"], "source": it["source"], "context": it["context"]}
        for it in batch
    ]
    user_msg = (
        "Translate each item's \"source\" into Arabic. Return one object per item with "
        "its original \"key\" and the Arabic \"translation\".\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        output_format=TranslationBatch,
    )
    result = response.parsed_output
    return {item.key: item.translation for item in result.items}


# ------------------------------------------------------------------
# البرنامج الرئيسي
# ------------------------------------------------------------------
def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("❌ يرجى ضبط متغيّر البيئة ANTHROPIC_API_KEY أولاً.")

    print(f"📂 قراءة الملف: {INPUT_CSV}")
    rows = read_csv_any_encoding(INPUT_CSV)
    if not rows:
        sys.exit("❌ الملف فارغ!")
    source_col = len(rows[0]) - 1  # آخر عمود = النص الإنجليزي

    # جمع الصفوف التي تحتاج ترجمة
    to_translate: List[dict] = []
    for i, row in enumerate(rows):
        if len(row) <= source_col:
            continue
        source = row[source_col].strip()
        current = row[TRANSLATION_COL].strip()
        context = row[CONTEXT_COL].strip() if len(row) > CONTEXT_COL else ""
        if not source:
            continue
        if current and not OVERWRITE_EXISTING:
            continue
        if is_do_not_translate(context):
            continue
        to_translate.append(
            {"row": i, "key": row[KEY_COL], "source": source, "context": context}
        )

    print(f"🌐 عدد النصوص التي تحتاج ترجمة: {len(to_translate)}")
    if not to_translate:
        write_csv(OUTPUT_CSV, rows)
        print(f"✨ لا يوجد جديد. تم حفظ نسخة في: {OUTPUT_CSV}")
        return

    client = anthropic.Anthropic()  # يقرأ المفتاح من ANTHROPIC_API_KEY
    cache = load_cache()

    # الترجمة على دفعات (مع تخطّي ما هو موجود في الكاش)
    pending = [it for it in to_translate if it["key"] not in cache]
    total_batches = (len(pending) + BATCH_SIZE - 1) // BATCH_SIZE
    for b in range(total_batches):
        batch = pending[b * BATCH_SIZE : (b + 1) * BATCH_SIZE]
        print(f"🔄 الدفعة {b + 1}/{total_batches} ({len(batch)} نص) ...")
        try:
            translated = translate_batch(client, batch)
        except anthropic.APIError as e:
            print(f"   ⚠️ خطأ في الـ API: {e}. سيتم تخطّي هذه الدفعة.")
            continue
        cache.update(translated)
        save_cache(cache)  # حفظ فوري لإتاحة الاستئناف

    # تطبيق الترجمات + التحقق من سلامة المتغيّرات والوسوم
    filled = warnings = 0
    for it in to_translate:
        ar = cache.get(it["key"])
        if not ar:
            continue
        src = it["source"]
        if placeholders(src) != placeholders(ar):
            print(f"   ⚠️ متغيّرات غير متطابقة في: {it['key']}")
            warnings += 1
        # تنبيه فقط لوسوم HTML الحقيقية (نتجاهل نصوصاً مثل <No title>)
        if html_tags(src) and html_tags(src) != html_tags(ar):
            print(f"   ⚠️ وسوم HTML غير متطابقة في: {it['key']}")
            warnings += 1
        rows[it["row"]][TRANSLATION_COL] = ar
        filled += 1

    write_csv(OUTPUT_CSV, rows)
    print(f"\n✅ تمت ترجمة {filled} صفاً (تحذيرات: {warnings}).")
    print(f"💾 تم حفظ الملف: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
