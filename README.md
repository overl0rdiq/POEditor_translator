# POEditor AI Translate

سكربت Python يترجم النصوص غير المترجمة في ملفات **POEditor** ترجمةً سياقيةً عالية الجودة
باستخدام **Claude API** (نموذج `claude-opus-4-8`) — بديل أفضل من الترجمة الآلية التقليدية.

يحافظ الكود على:

- المتغيّرات مثل `{current}` و `{total}`
- وسوم HTML مثل `<strong>` و `<br/>`
- أسطر `\n` الجديدة
- أسماء العلامات التجارية (Tuta، Gmail، IMAP ...)

ويتخطّى النصوص المُعلَّمة `do not translate` / `deprecated` في حقل السياق.

## المتطلبات

```bash
pip install -r requirements.txt
```

## المفتاح

المفتاح **لا يوجد داخل الكود**، يُقرأ من متغيّر البيئة:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

احصل على مفتاح من: https://console.anthropic.com

## التشغيل

```bash
python ai_translate.py
```

النتيجة: ملف جديد `Tuta_Client_Arabic_AI_Translated.csv` بالصيغة نفسها، جاهز للرفع على POEditor.

## الإعدادات

عدّلها من أعلى ملف [`ai_translate.py`](ai_translate.py):

| الإعداد | الوصف |
|---------|-------|
| `INPUT_CSV` | ملف POEditor المصدر |
| `OUTPUT_CSV` | اسم الملف الناتج |
| `MODEL` | نموذج Claude المستخدَم |
| `BATCH_SIZE` | عدد النصوص في كل طلب (أصغر = أدق، أكبر = أسرع) |
| `OVERWRITE_EXISTING` | `True` لإعادة ترجمة كل شيء حتى المترجَم مسبقاً |
| `GLOSSARY` | مصطلحات موحّدة للحفاظ على اتساق الترجمة |

## بنية العمود في CSV

الأعمدة المتوقّعة (صيغة تصدير POEditor):

```
key , translation , (فارغ) , (فارغ) , context , source(EN)
```

عمود المصدر هو آخر عمود. عدّل `KEY_COL` / `TRANSLATION_COL` / `CONTEXT_COL` إن اختلفت بنية ملفك.

## الاستئناف بعد الانقطاع

يُحفظ التقدّم في `.translation_cache.json` بعد كل دفعة، فإذا توقّف السكربت لأي سبب
أعِد تشغيله وسيكمل من حيث توقّف دون إعادة ترجمة ما تم.
```
