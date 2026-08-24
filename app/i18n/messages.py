"""Backend user-facing strings that appear in the UI or fallback lessons."""

from __future__ import annotations

from typing import Any

from app.i18n.language import normalize_language

_EN: dict[str, str] = {
    "refusal": "I couldn't find enough information in the study materials.",
    "recommend_weak": (
        "Based on your recent performance, you should review {topic} "
        "before attempting another {subject} exam."
    ),
    "recommend_start": "Start a focused lecture in Learn, then try adaptive practice.",
    "continue_open_learn": "Open Learn",
    "continue_course": "Continue {title} (lesson {index} of {total})",
    "goal_today_default": "Complete one focused practice set",
    "goal_weekly_default": "Improve one weak topic",
    "plan_title": "Today's Plan",
    "plan_lesson": "Review a weak topic in Learn",
    "plan_practice": "Adaptive practice (10 questions)",
    "plan_exam": "Short WAEC-style mock (10 questions)",
    "fallback_intro": "Let's learn about {title} together. I'll keep it clear and exam-focused.",
    "fallback_obj_1": "Understand the main idea of {title}",
    "fallback_obj_2": "See a worked example in WAEC/NECO style",
    "fallback_obj_3": "Check your understanding with a short practice question",
    "fallback_heading_idea": "The big idea",
    "fallback_body_idea": (
        "{title} is an important O-Level topic. "
        "We'll build from the definition to an exam-style example."
    ),
    "fallback_heading_remember": "How to remember it",
    "fallback_body_remember": (
        "Write the key definition in your own words, then try one past-question style "
        "problem. Short, steady practice beats cramming."
    ),
    "fallback_problem": "State one key point about {title}.",
    "fallback_step_1": "Read the question carefully.",
    "fallback_step_2": "Recall the definition or rule.",
    "fallback_step_3": "Write a clear, exam-style sentence.",
    "fallback_answer": "A correct answer names the core idea of {title} accurately.",
    "fallback_check_q": "In one sentence, what is {title}?",
    "fallback_check_a": "A short correct definition of {title}.",
    "fallback_hint": "Start with: 'It is…' and keep it to one clear idea.",
    "fallback_practice_q": "Which statement best describes {title}?",
    "fallback_opt_a": "A. A clear definition related to {title}",
    "fallback_opt_b": "B. An unrelated everyday opinion",
    "fallback_opt_c": "C. A random number with no units",
    "fallback_opt_d": "D. A joke answer",
    "fallback_explain": (
        "Option A is closest to the syllabus idea of {title}. "
        "In WAEC/NECO, always choose the precise definition."
    ),
    "fallback_sum_1": "{title} has a clear definition you can write in one sentence.",
    "fallback_sum_2": "Worked examples show the method examiners expect.",
    "fallback_sum_3": "Revision cards help you remember the key point quickly.",
    "fallback_rev_front": "What should you remember about {title}?",
    "fallback_rev_back": "Recall the definition and one exam tip for {title}.",
    "fallback_ready": "Lesson ready: {title}",
    "format_fallback_reason": (
        "I prepared a clear lesson outline for you. "
        "Some details may be general - ask a follow-up if you want more depth."
    ),
    "practice_ok": "Nice work - keep going with a similar question.",
    "practice_retry": "Mistakes are how mastery grows. Read the explanation, then try another.",
    "practice_correct": "Correct. {explanation}",
    "practice_correct_extra": "Well done - keep reinforcing this topic.",
    "practice_wrong": "Not quite. The answer is {expected}. {explanation}",
    "practice_wrong_extra": "Review the idea and try a similar question.",
    "no_questions": "No questions available for filters",
    "fallback_empty_topic": "Tell me what topic you'd like to learn and I'll teach it step by step.",
    "fallback_title": "Today's lesson",
    "outline_what": "What is {topic}?",
    "outline_laws": "Laws and rules in {topic}",
    "outline_method_a": "First method for {topic}",
    "outline_method_b": "Second method for {topic}",
    "outline_calc": "Calculations in {topic}",
    "outline_mistakes": "Common mistakes in {topic}",
    "outline_technique": "Exam technique for {topic}",
    "outline_typical": "Typical questions on {topic}",
    "outline_exam": "Exam questions on {topic}",
    "outline_worked": "Worked examples: {topic}",
    "outline_recap": "Revision recap: {topic}",
    "outline_r_foundation": "Foundation - terms and definitions from the syllabus.",
    "outline_r_laws": "The laws, rules, or principles examiners expect you to state.",
    "outline_r_method_a": "Method A - the first main procedure for exam questions.",
    "outline_r_method_b": "Method B - an alternative approach from the syllabus.",
    "outline_r_calc": "Numbers, formulae, and how to set out working.",
    "outline_r_mistakes": "Misconceptions to unlearn before the assessment.",
    "outline_r_technique": "How to read the question and earn method marks.",
    "outline_r_typical": "The question shapes WAEC, NECO, and JAMB reuse.",
    "outline_r_exam": "Bank questions to check exam readiness.",
    "outline_r_worked": "Step-by-step solutions before independent practice.",
    "outline_r_recap": "Key facts to remember under exam time pressure.",
    "outline_skip_mastery": "Mastery already {score:.0%}",
    "outline_skip_confident": "You marked yourself as confident on this topic.",
    "outline_obj": "Help the student {goal} {topic} using {style_note}.",
    "outline_obj_exam": "Prepare the student to answer {subject} exam questions on {topic}.",
    "style_worked": "step-by-step with worked examples",
    "style_examples": "examples first, then the rule",
    "style_visual": "visual explanations and diagrams where possible",
    "style_exam": "exam-focused technique",
    "style_clear": "clear explanations",
}

_HA: dict[str, str] = {
    "refusal": "Ban sami isasshen bayani a cikin kayan karatu ba.",
    "recommend_weak": (
        "Dangane da aikin da ka yi kwanan nan, ya kamata ka sake nazarin {topic} "
        "kafin ka sake gwajin {subject}."
    ),
    "recommend_start": "Fara da darasi a Koyo, sa'an nan ka yi horon aiki.",
    "continue_open_learn": "Bude Koyo",
    "continue_course": "Ci gaba da {title} (darasi {index} cikin {total})",
    "goal_today_default": "Kammala saitin horon aiki guda",
    "goal_weekly_default": "Inganta batu guda da yake da wahala",
    "plan_title": "Shirin yau",
    "plan_lesson": "Sake nazarin batu mai wahala a Koyo",
    "plan_practice": "Horon aiki (tambayoyi 10)",
    "plan_exam": "Gajeren gwajin WAEC (tambayoyi 10)",
    "fallback_intro": "Mu koyi {title} tare. Zan yi bayani a fili, bisa bukatar jarabawa.",
    "fallback_obj_1": "Fahimci babban ra'ayin {title}",
    "fallback_obj_2": "Ga misalin da aka yi aiki a salon WAEC/NECO",
    "fallback_obj_3": "Gwada fahimtar ka da gajeren tambaya",
    "fallback_heading_idea": "Babban ra'ayi",
    "fallback_body_idea": (
        "{title} batu ne mai muhimmanci a O-Level. "
        "Za mu tashi daga ma'anar zuwa misalin salon jarabawa."
    ),
    "fallback_heading_remember": "Yadda za ka tuna da shi",
    "fallback_body_remember": (
        "Rubuta ma'anar da kanka, sa'an nan ka gwada tambayar salon jarabawar da ta wuce. "
        "Gajeren aiki na yau da kullum ya fi tura kai."
    ),
    "fallback_problem": "Fadi muhimmin batu guda akan {title}.",
    "fallback_step_1": "Karanta tambayar a hankali.",
    "fallback_step_2": "Tuna ma'anar ko dokar.",
    "fallback_step_3": "Rubuta jumla mai tsabta a salon jarabawa.",
    "fallback_answer": "Amsa mai kyau tana kiran ainihin ra'ayin {title} daidai.",
    "fallback_check_q": "A jumla guda, menene {title}?",
    "fallback_check_a": "Gajeren ma'anar {title} daidai.",
    "fallback_hint": "Fara da: 'Shi ne…' kuma ka tsaya a ra'ayi guda.",
    "fallback_practice_q": "Wace magana ce ta fi bayyana {title}?",
    "fallback_opt_a": "A. Ma'anar da ta dace da {title}",
    "fallback_opt_b": "B. Ra'ayin yau da kullum wanda bai dace ba",
    "fallback_opt_c": "C. Lamba bazuwar ba tare da raka'a ba",
    "fallback_opt_d": "D. Amsar wasa",
    "fallback_explain": (
        "Zaɓi A shine mafi kusa da ra'ayin silabus na {title}. "
        "A WAEC/NECO, koyaushe ka zaɓi ma'anar da ta dace."
    ),
    "fallback_sum_1": "{title} yana da ma'anar da za ka iya rubutawa a jumla guda.",
    "fallback_sum_2": "Misalan da aka yi aiki suna nuna hanyar da masu jarabawa suke so.",
    "fallback_sum_3": "Katunan maimaitawa suna taimaka ka tuna muhimmin batu da sauri.",
    "fallback_rev_front": "Me ya kamata ka tuna akan {title}?",
    "fallback_rev_back": "Tuna ma'anar da shawarar jarabawa guda akan {title}.",
    "fallback_ready": "Darasi a shirye: {title}",
    "format_fallback_reason": (
        "Na shirya tsarin darasi a fili. "
        "Wasu bayanai na iya zama na gaba ɗaya - tambaya idan kana son zurfafa."
    ),
    "practice_ok": "Madalla - ci gaba da irin wannan tambaya.",
    "practice_retry": "Kuskure hanya ce ta ƙwarewa. Karanta bayanin, sa'an nan ka sake gwadawa.",
    "practice_correct": "Daidai. {explanation}",
    "practice_correct_extra": "Madalla - ci gaba da ƙarfafa wannan batu.",
    "practice_wrong": "Bai daidai ba. Amsa ita ce {expected}. {explanation}",
    "practice_wrong_extra": "Sake nazarin ra'ayin, sa'an nan ka gwada irin wannan tambaya.",
    "no_questions": "Babu tambayoyi don wannan zaɓi",
    "fallback_empty_topic": "Fada mini wane batu kake so ka koyi, zan koya maka mataki-mataki.",
    "fallback_title": "Darasin yau",
    "outline_what": "Menene {topic}?",
    "outline_laws": "Dokoki da ka'idoji a {topic}",
    "outline_method_a": "Hanya ta farko ta {topic}",
    "outline_method_b": "Hanya ta biyu ta {topic}",
    "outline_calc": "Lissafi a {topic}",
    "outline_mistakes": "Kurakuran da ake yawan yi a {topic}",
    "outline_technique": "Dabarun jarabawa na {topic}",
    "outline_typical": "Tambayoyin da aka saba yi akan {topic}",
    "outline_exam": "Tambayoyin jarabawa akan {topic}",
    "outline_worked": "Misalan da aka yi aiki: {topic}",
    "outline_recap": "Takaitaccen maimaitawa: {topic}",
    "outline_r_foundation": "Tushen - kalmomi da ma'anoni daga silabus.",
    "outline_r_laws": "Dokoki, ka'idoji, ko ƙa'idodin da masu jarabawa suke son ka fada.",
    "outline_r_method_a": "Hanya A - babban tsari na farko don tambayoyin jarabawa.",
    "outline_r_method_b": "Hanya B - wata hanya daga silabus.",
    "outline_r_calc": "Lambobi, dabarun lissafi, da yadda za a tsara aiki.",
    "outline_r_mistakes": "Kuskuren da ya kamata a gyara kafin gwaji.",
    "outline_r_technique": "Yadda za a karanta tambaya da samun maki na hanya.",
    "outline_r_typical": "Siffofin tambaya da WAEC, NECO, da JAMB suke sake amfani da su.",
    "outline_r_exam": "Tambayoyin banki don gwada shirye-shiryen jarabawa.",
    "outline_r_worked": "Amsoshi mataki-mataki kafin aiki kai tsaye.",
    "outline_r_recap": "Muhimman abubuwan da za a tuna a lokacin jarabawa.",
    "outline_skip_mastery": "An riga an ƙware {score:.0%}",
    "outline_skip_confident": "Ka nuna cewa kana da kwarin gwiwa a wannan batu.",
    "outline_obj": "Taimaki ɗalibin ya {goal} {topic} ta amfani da {style_note}.",
    "outline_obj_exam": "Shirya ɗalibin ya amsa tambayoyin jarabawar {subject} akan {topic}.",
    "style_worked": "mataki-mataki tare da misalan da aka yi aiki",
    "style_examples": "misalai da farko, sa'an nan ƙa'idar",
    "style_visual": "bayani na gani inda ya dace",
    "style_exam": "dabarun jarabawa",
    "style_clear": "bayani mai tsabta",
}

_TABLE: dict[str, dict[str, str]] = {"English": _EN, "Hausa": _HA}


def ui_string(key: str, language: Any = None, **kwargs: Any) -> str:
    """Format a backend UI / fallback string in English or Hausa."""
    lang = normalize_language(language)
    table = _TABLE.get(lang) or _EN
    template = table.get(key) or _EN.get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            return template
    return template
