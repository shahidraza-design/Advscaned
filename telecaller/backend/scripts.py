"""
scripts.py — everything the agent *says*, in English, Hindi and Bengali.

The dialog engine never hard-codes a sentence; it asks this module for a line.
That means a non-developer can rewrite the whole call script (or add a new
language) by editing one file — no model, no training, no cost.

Every line is {en, hi, bn}. Missing translations fall back to English.
`{name}`, `{slot}`, `{agent}`, `{company}` and `{email}` are filled in at
speak-time by DialogEngine.
"""
from __future__ import annotations

# --------------------------------------------------------------------- business
# Edit these in Settings → the agent's personality and offer come from here.
BUSINESS_DEFAULTS: dict = {
    "company": "Advscaned",
    "product": "QPaper AI",
    "agent_name": "Aarohi",
    "value_prop": (
        "we turn a photo of any textbook page into a ready-to-print question paper, "
        "with diagrams and equations already attached"
    ),
    "offer": "a free 15-minute online demo on one of your own chapters",
    "offer_hi": "आपके ही किसी चैप्टर पर पंद्रह मिनट का मुफ़्त ऑनलाइन डेमो",
    "offer_bn": "আপনার নিজের কোনো চ্যাপ্টারে পনেরো মিনিটের ফ্রি অনলাইন ডেমো",
    "value_prop_hi": "हम किसी भी किताब के पेज की फ़ोटो से छपाई-योग्य क्वेश्चन पेपर बना देते हैं, डायग्राम और फ़ॉर्मूले पहले से जुड़े हुए",
    "value_prop_bn": "আমরা যেকোনো বইয়ের পাতার ছবি থেকে ছাপার উপযোগী প্রশ্নপত্র বানিয়ে দিই, ডায়াগ্রাম আর ফর্মুলা আগেই জুড়ে দেওয়া থাকে",
    "demo_slots": ["tomorrow at 4 pm", "Friday at 11 am"],
    "demo_slots_hi": ["कल शाम 4 बजे", "शुक्रवार सुबह 11 बजे"],
    "demo_slots_bn": ["কাল বিকেল ৪টে", "শুক্রবার সকাল ১১টা"],
    "languages": ["en", "hi", "bn"],
    "default_language": "en",
    "calling_hours": "10:00-19:00",
    "record_notice": "This call may be recorded for quality purposes.",
    "human_transfer_number": "",
    "webhook_url": "",
    "llm_provider": "off",           # off | ollama | openai | gemini
    "llm_base_url": "http://localhost:11434",
    "llm_model": "llama3.1",
    "llm_api_key": "",
    "max_discovery_questions": 2,
}

# ------------------------------------------------------------------------ lines
LINES: dict[str, dict[str, str]] = {
    "greeting": {
        "en": "Hi, this is {agent} calling from {company}.",
        "hi": "नमस्ते, मैं {agent} बोल रही हूँ, {company} से।",
        "bn": "নমস্কার, আমি {agent} বলছি, {company} থেকে।",
    },
    "permission": {
        "en": "Am I speaking with {name}? I'll take just thirty seconds — is now a good time?",
        "hi": "क्या मेरी बात {name} जी से हो रही है? सिर्फ़ तीस सेकंड लूँगी — अभी बात करना ठीक रहेगा?",
        "bn": "আমি কি {name} দির সঙ্গে কথা বলছি? মাত্র ত্রিশ সেকেন্ড সময় নেব — এখন কথা বলতে সুবিধা হবে?",
    },
    "purpose": {
        "en": "Sure — {value_prop}. Teachers just tick the questions they want and export to Word or PDF.",
        "hi": "जी, {value_prop}। टीचर सिर्फ़ सवाल टिक करते हैं और Word या PDF में एक्सपोर्ट कर देते हैं।",
        "bn": "হ্যাঁ, {value_prop}। শিক্ষক শুধু প্রশ্ন টিক করেন আর Word বা PDF-এ এক্সপোর্ট করেন।",
    },
    "discovery_1": {
        "en": "Before I go on — which classes does your school handle, and how do teachers make papers today?",
        "hi": "पहले ये बताइए — आपके स्कूल में कौन-कौन सी क्लासें हैं, और अभी पेपर कैसे बनते हैं?",
        "bn": "আগে বলুন — আপনার স্কুলে কোন কোন ক্লাস আছে, আর এখন প্রশ্নপত্র কীভাবে তৈরি হয়?",
    },
    "discovery_2": {
        "en": "And roughly how many papers does your team set in a term?",
        "hi": "और एक टर्म में लगभग कितने पेपर बनते हैं?",
        "bn": "আর একটা টার্মে প্রায় কতগুলো প্রশ্নপত্র হয়?",
    },
    "discovery_3": {
        "en": "Last one — would you want this in place before the next exam cycle?",
        "hi": "आख़िरी बात — क्या अगले एग्ज़ाम से पहले ये चालू हो जाना चाहिए?",
        "bn": "শেষ কথা — পরের পরীক্ষার আগে এটা চালু হয়ে যাওয়া দরকার?",
    },
    "ack_then": {
        "en": "Got it.",
        "hi": "समझ गई।",
        "bn": "বুঝেছি।",
    },
    "pitch_small": {
        "en": "Most schools like yours start with one subject and one class. A teacher photographs the chapter, and in about a minute there's a paper with the diagrams already in place — nothing retyped, exported straight to Word or PDF.",
        "hi": "आपके जैसे स्कूल एक सब्जेक्ट और एक क्लास से शुरू करते हैं। टीचर चैप्टर की फ़ोटो लेते हैं, एक मिनट में डायग्राम वाला पेपर तैयार — कुछ टाइप नहीं करना, सीधे Word या PDF।",
        "bn": "আপনার মতো স্কুল একটা বিষয় আর একটা ক্লাস দিয়ে শুরু করে। শিক্ষক চ্যাপ্টারের ছবি তোলেন, এক মিনিটে ডায়াগ্রামসহ প্রশ্নপত্র তৈরি — কিছু টাইপ করতে হয় না, সরাসরি Word বা PDF।",
    },
    "pitch_big": {
        "en": "For a school your size the saving shows up in exam season — one photo per chapter, and every diagram, formula and table lands next to its question. Papers that took two days come out in an afternoon.",
        "hi": "आपके स्कूल के साइज़ में फ़ायदा एग्ज़ाम सीज़न में दिखता है — हर चैप्टर की एक फ़ोटो, और हर डायग्राम, फ़ॉर्मूला और टेबल अपने सवाल के साथ। जो पेपर दो दिन लेते थे, वो एक दोपहर में।",
        "bn": "আপনার স্কুলের আকারে সুবিধাটা পরীক্ষার সময়ে বোঝা যায় — প্রতি চ্যাপ্টারের একটা ছবি, আর প্রতিটি ডায়াগ্রাম, ফর্মুলা আর টেবিল নিজের প্রশ্নের পাশে। যে প্রশ্নপত্রে দু’দিন লাগত, সেটা এক বিকেলে।",
    },
    "close_1": {
        "en": "Rather than explain on the phone, let me show you — {offer}. Would {slot1}, or {slot2}, work better?",
        "hi": "फ़ोन पर समझाने के बजाय दिखा दूँ — {offer}। {slot1} या {slot2}, क्या ठीक रहेगा?",
        "bn": "ফোনে বোঝানোর বদলে দেখিয়ে দিই — {offer}। {slot1} বা {slot2}, কোনটা সুবিধা?",
    },
    "close_2": {
        "en": "So — {slot1}, or {slot2}?",
        "hi": "तो — {slot1} या {slot2}?",
        "bn": "তাহলে — {slot1} বা {slot2}?",
    },
    "booked": {
        "en": "Perfect, I've noted {slot}. I'll send the meeting link on WhatsApp right after this call. Thank you, {name}.",
        "hi": "बहुत बढ़िया, {slot} नोट कर लिया। मीटिंग लिंक व्हाट्सऐप पर भेज दूँगी। धन्यवाद, {name} जी।",
        "bn": "দারুণ, {slot} লিখে নিলাম। মিটিং লিংক হোয়াটসঅ্যাপে পাঠিয়ে দেব। ধন্যবাদ, {name} দি।",
    },
    "followup_email": {
        "en": "Happy to — what's the best email for you?",
        "hi": "बिलकुल — ईमेल आईडी बता दीजिए, आज ही भेज दूँगी।",
        "bn": "অবশ্যই — ইমেল আইডিটা বলুন, আজই পাঠিয়ে দেব।",
    },
    "followup_email_ack": {
        "en": "Noted — {email}. I'll send a one-page summary and a ninety-second demo video today. Thank you, {name}.",
        "hi": "नोट कर लिया — {email}। आज ही एक पेज का सार और डेमो वीडियो भेज दूँगी। धन्यवाद, {name} जी।",
        "bn": "লিখে নিলাম — {email}। আজই এক পাতার সারসংক্ষেপ আর ডেমো ভিডিও পাঠিয়ে দেব। ধন্যবাদ, {name} দি।",
    },
    "callback_confirm": {
        "en": "Of course — I'll call you back {slot}. Have a good day, {name}.",
        "hi": "ठीक है — मैं {slot} पर कॉल करूँगी। आपका दिन शुभ हो, {name} जी।",
        "bn": "ঠিক আছে — আমি {slot} ফোন করব। আপনার দিন ভালো কাটুক, {name} দি।",
    },
    "busy_ack": {
        "en": "No problem at all — I can hear you're busy.",
        "hi": "कोई बात नहीं, समझ सकती हूँ आप व्यस्त हैं।",
        "bn": "কোনো সমস্যা নেই, বুঝতে পারছি আপনি ব্যস্ত।",
    },
    "not_interested_close": {
        "en": "I understand — I won't take more of your time. Thanks for picking up, {name}.",
        "hi": "समझ गई — आपका समय नहीं लूँगी। फ़ोन उठाने के लिए धन्यवाद, {name} जी।",
        "bn": "বুঝেছি — আপনার সময় নেব না। ফোন ধরার জন্য ধন্যবাদ, {name} দি।",
    },
    "dnc_close": {
        "en": "Sorry to have disturbed you. I've removed your number from our list — you won't hear from us again.",
        "hi": "क्षमा करें, परेशान करने के लिए माफ़ी। मैंने आपका नंबर लिस्ट से हटा दिया है — दोबारा कॉल नहीं आएगा।",
        "bn": "দুঃখিত, বিরক্ত করার জন্য ক্ষমা করবেন। আপনার নম্বর লিস্ট থেকে সরিয়ে দিয়েছি — আর ফোন আসবে না।",
    },
    "wrong_number_close": {
        "en": "Apologies for the wrong number — I'll correct our records. Have a good day.",
        "hi": "ग़लत नंबर के लिए माफ़ी — रिकॉर्ड ठीक कर लूँगी। आपका दिन शुभ हो।",
        "bn": "ভুল নম্বরের জন্য দুঃখিত — রেকর্ড ঠিক করে নিচ্ছি। আপনার দিন ভালো কাটুক।",
    },
    "repeat_ack": {
        "en": "Sorry about that — let me say it again.",
        "hi": "माफ़ी, फिर से कहती हूँ।",
        "bn": "ক্ষমা করবেন, আবার বলছি।",
    },
    "human_transfer": {
        "en": "Of course — connecting you to my colleague now. One moment.",
        "hi": "जी, अभी अपने साथी से जोड़ रही हूँ। एक मिनट।",
        "bn": "অবশ্যই — এখনই আমার সহকর্মীর সঙ্গে যোগ দিচ্ছি। এক মিনিট।",
    },
    "unclear": {
        "en": "Sorry, the line isn't very clear — could you say that in a few words?",
        "hi": "माफ़ी, आवाज़ साफ़ नहीं आ रही — थोड़े शब्दों में बता सकते हैं?",
        "bn": "ক্ষমা করবেন, শব্দ স্পষ্ট আসছে না — একটু কম কথায় বলবেন?",
    },
    "lang_switch": {
        "en": "Of course, let's carry on in English.",
        "hi": "जी, हिंदी में बात करते हैं।",
        "bn": "ঠিক আছে, বাংলায় কথা বলি।",
    },
    "answer_ack": {
        "en": "Thank you, that's helpful.",
        "hi": "धन्यवाद, ये काम की बात है।",
        "bn": "ধন্যবাদ, কাজের তথ্য।",
    },
    "audio_ok": {
        "en": "Yes, I can hear you clearly — please go ahead.",
        "hi": "जी, आपकी आवाज़ साफ़ आ रही है — बोलिए।",
        "bn": "হ্যাঁ, আপনার কথা স্পষ্ট শুনছি — বলুন।",
    },
    "thanks": {
        "en": "You're welcome.",
        "hi": "कोई बात नहीं।",
        "bn": "কিছু মনে করবেন না।",
    },
    "who_is_this": {
        "en": "This is {agent} from {company} — we work with schools on question-paper software.",
        "hi": "मैं {agent} बोल रही हूँ, {company} से — हम स्कूलों के लिए क्वेश्चन पेपर सॉफ़्टवेयर बनाते हैं।",
        "bn": "আমি {agent}, {company} থেকে — আমরা স্কুলের জন্য প্রশ্নপত্র সফটওয়্যার বানাই।",
    },
    "purpose_short": {
        "en": "It's about {product} — school question papers made from a photo of the textbook page.",
        "hi": "{product} के बारे में — किताब के पेज की फ़ोटो से स्कूल का क्वेश्चन पेपर।",
        "bn": "{product} নিয়ে — বইয়ের পাতার ছবি থেকে স্কুলের প্রশ্নপত্র।",
    },
    "interest_ack": {
        "en": "Good — then one quick question.",
        "hi": "अच्छा — तो एक छोटा सवाल।",
        "bn": "ভালো — তাহলে একটা ছোট প্রশ্ন।",
    },
    "demo_accept": {
        "en": "Great — the demo is fifteen minutes, on Zoom or Google Meet, whichever you prefer.",
        "hi": "बहुत बढ़िया — डेमो पंद्रह मिनट का, Zoom या Google Meet, जो आपको ठीक लगे।",
        "bn": "দারুণ — ডেমো পনেরো মিনিটের, Zoom বা Google Meet, যেটা সুবিধা।",
    },
    "hold_on": {
        "en": "Sure, take your time.",
        "hi": "जी, आराम से।",
        "bn": "অবশ্যই, সময় নিন।",
    },
}

# -------------------------------------------------------------------- objections
# acknowledge → reframe → ask.  Never argue with the customer.
OBJECTIONS: dict[str, dict] = {
    "price": {
        "label": "price",
        "reply": {
            "en": "There's no charge for the pilot — one subject, one class, for two weeks. After that it's a per-school licence, not per teacher, and I'll give you exact numbers on the demo.",
            "hi": "पायलट का कोई चार्ज नहीं — एक सब्जेक्ट, एक क्लास, दो हफ़्ते। उसके बाद पूरे स्कूल का लाइसेंस होता है, हर टीचर का नहीं — डेमो में पक्की रकम बता दूँगी।",
            "bn": "পাইলটের জন্য কোনো টাকা লাগে না — একটা বিষয়, একটা ক্লাস, দুই সপ্তাহ। তারপর পুরো স্কুলের লাইসেন্স, প্রতি শিক্ষকের নয় — ডেমোতে সঠিক অঙ্কটা বলে দেব।",
        },
    },
    "have_vendor": {
        "label": "already has a tool",
        "reply": {
            "en": "Fair enough — most schools we speak to already had something. The difference is that diagrams and equations get paired automatically, so nothing is typed twice. Would a fifteen-minute comparison help?",
            "hi": "ठीक है — जिन स्कूलों से बात होती है, उनमें से कई के पास पहले से कुछ था। फ़र्क़ ये है कि डायग्राम और फ़ॉर्मूला अपने आप जुड़ते हैं, दोबारा टाइप नहीं करना पड़ता। पंद्रह मिनट की तुलना कर लें?",
            "bn": "ঠিক আছে — অনেক স্কুলেরই আগে কিছু ছিল। পার্থক্য হলো ডায়াগ্রাম আর ফর্মুলা নিজে থেকে জুড়ে যায়, দু’বার টাইপ করতে হয় না। পনেরো মিনিটের তুলনা করে দেখবেন?",
        },
    },
    "trust": {
        "label": "trust / data safety",
        "reply": {
            "en": "Fair question. Pages are processed on your own machine or on servers in India, no student data is needed at all, and you can delete a document whenever you like.",
            "hi": "अच्छा सवाल। पेज आपकी मशीन पर या भारत के सर्वर पर प्रोसेस होते हैं, स्टूडेंट डेटा की ज़रूरत नहीं, और आप कभी भी डॉक्यूमेंट डिलीट कर सकते हैं।",
            "bn": "ভালো প্রশ্ন। পাতা আপনার নিজের মেশিনে বা ভারতের সার্ভারে প্রসেস হয়, ছাত্রদের ডেটা লাগে না, আর আপনি যখন চান ডকুমেন্ট ডিলিট করতে পারেন।",
        },
    },
    "think": {
        "label": "needs to think",
        "reply": {
            "en": "That's fair. What's the one thing you'd want cleared up before deciding?",
            "hi": "जायज़ बात है। कौन सी एक बात साफ़ हो जाए तो फ़ैसला आसान होगा?",
            "bn": "যুক্তিসঙ্গত। কোন একটা বিষয় পরিষ্কার হলে সিদ্ধান্ত সহজ হবে?",
        },
    },
    "no_budget": {
        "label": "no budget this year",
        "reply": {
            "en": "Understood — the pilot costs nothing, so it can sit in this year's budget as a trial. If it saves your teachers a week in exam season, you can plan the licence for next term.",
            "hi": "समझ गई — पायलट में कुछ ख़र्च नहीं, इसलिए इसे इसी साल ट्रायल की तरह रख सकते हैं। अगर एग्ज़ाम में टीचर्स का एक हफ़्ता बचे, तो अगले टर्म में लाइसेंस सोच लें।",
            "bn": "বুঝেছি — পাইলটে খরচ নেই, তাই এটা এই বছরেই ট্রায়াল হিসেবে রাখা যায়। পরীক্ষার সময় শিক্ষকদের এক সপ্তাহ বাঁচলে পরের টার্মে লাইসেন্সের কথা ভাবতে পারেন।",
        },
    },
    "no_time": {
        "label": "no time",
        "reply": {
            "en": "I completely understand — that's exactly why I'm not asking for a meeting today. Fifteen minutes, once, and you'll know whether it's worth your teachers' time.",
            "hi": "समझ सकती हूँ — इसीलिए आज मीटिंग नहीं माँग रही। पंद्रह मिनट, एक बार, और आप ख़ुद जान जाएँगे कि टीचर्स का समय बचेगा या नहीं।",
            "bn": "পুরোপুরি বুঝতে পারছি — এইজন্যই আজ মিটিং চাইছি না। পনেরো মিনিট, একবার, আর আপনি নিজেই বুঝে যাবেন শিক্ষকদের সময় বাঁচবে কি না।",
        },
    },
    "already_tried": {
        "label": "tried something like this",
        "reply": {
            "en": "That's useful to know — what went wrong with it? Usually it's the diagrams, or teachers having to retype everything.",
            "hi": "जानकर अच्छा लगा — उसमें दिक्कत क्या थी? अक्सर डायग्राम, या टीचर्स को सब दोबारा टाइप करना पड़ता है।",
            "bn": "জেনে ভালো লাগল — ওটাতে সমস্যা কী হয়েছিল? সাধারণত ডায়াগ্রাম, বা শিক্ষকদের সব আবার টাইপ করতে হয়।",
        },
    },
    "send_info": {
        "label": "send information instead",
        "reply": {
            "en": "Happy to — what's the best email for you?",
            "hi": "बिलकुल — कौन सी ईमेल आईडी सबसे अच्छी रहेगी?",
            "bn": "অবশ্যই — কোন ইমেল আইডি সবচেয়ে ভালো হবে?",
        },
    },
}

# ------------------------------------------------------- discovery / next question
HINTS = {
    "OPENING": "If they hesitate, ask permission once — never push past a 'no'.",
    "DISCOVERY": "One question per turn. Let silence do the work.",
    "PITCH": "Tie the benefit to the class size you just heard.",
    "OBJECTION": "Acknowledge, reframe, then ask a question — don't argue.",
    "CLOSE": "Give two concrete slots, not 'sometime next week'.",
    "WRAP": "Confirm the next step in one sentence, then end.",
}

# ------------------------------------------------------------------ quick chips
QUICK_REPLIES = {
    "OPENING": {
        "en": ["Yes, speaking", "Who is this?", "I'm busy right now", "Not interested"],
        "hi": ["हाँ, बोल रहा हूँ", "कौन बोल रहे हैं?", "अभी व्यस्त हूँ", "दिलचस्पी नहीं है"],
        "bn": ["হ্যাঁ, বলছি", "কে বলছেন?", "এখন ব্যস্ত আছি", "আগ্রহ নেই"],
    },
    "DISCOVERY": {
        "en": ["Classes 6 to 10", "We type papers in Word", "About 40 papers a term", "How does it work?"],
        "hi": ["क्लास 6 से 10", "Word में टाइप करते हैं", "टर्म में लगभग 40 पेपर", "ये कैसे काम करता है?"],
        "bn": ["ক্লাস ৬ থেকে ১০", "Word-এ টাইপ করি", "টার্মে প্রায় ৪০টা", "এটা কীভাবে কাজ করে?"],
    },
    "PITCH": {
        "en": ["How much does it cost?", "We already use a tool", "Send me details", "Sounds useful"],
        "hi": ["कितने का है?", "हमारे पास पहले से सॉफ़्टवेयर है", "डिटेल भेज दीजिए", "अच्छा लग रहा है"],
        "bn": ["কত টাকা?", "আমাদের আগেই একটা সফটওয়্যার আছে", "বিস্তারিত পাঠান", "ভালো লাগছে"],
    },
    "CLOSE": {
        "en": ["Tomorrow 4 pm works", "Friday 11 am is fine", "Send details instead", "I need to think"],
        "hi": ["कल 4 बजे ठीक है", "शुक्रवार 11 बजे चलेगा", "डिटेल भेज दीजिए", "सोचना पड़ेगा"],
        "bn": ["কাল ৪টে ঠিক আছে", "শুক্রবার ১১টা চলবে", "বিস্তারিত পাঠান", "ভেবে দেখতে হবে"],
    },
    "WRAP": {
        "en": ["Thank you", "Okay, bye"],
        "hi": ["धन्यवाद", "ठीक है, बाय"],
        "bn": ["ধন্যবাদ", "ঠিক আছে, বাই"],
    },
}
