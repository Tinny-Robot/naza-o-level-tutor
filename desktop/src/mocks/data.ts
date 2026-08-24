/** Presentation fixtures for Home / Achievements / Profile (non-AI screens). */

export const student = {
  name: "Ada",
  level: 12,
  xp: 2450,
  xpToNext: 3000,
  streak: 7,
  goalToday: "Complete 1 Physics lesson + 10 flashcards",
  goalProgress: 62,
};

export const subjects = [
  { id: "english", name: "English", mastery: 78, color: "#3B82F6", topic: "Concord" },
  { id: "mathematics", name: "Mathematics", mastery: 64, color: "#7C3AED", topic: "Quadratics" },
  { id: "physics", name: "Physics", mastery: 71, color: "#22D3EE", topic: "Refraction" },
  { id: "chemistry", name: "Chemistry", mastery: 58, color: "#10B981", topic: "Electrolysis" },
];

export const recentActivity = [
  { id: 1, label: "Revised Ohm’s Law flashcards", time: "12 min ago", xp: 40 },
  { id: 2, label: "Asked AI Tutor about subject-verb concord", time: "1 hr ago", xp: 25 },
  { id: 3, label: "Quiz: WAEC Physics 2022 - 8/10", time: "Yesterday", xp: 80 },
];

export const achievements = [
  { id: "streak7", title: "Week Warrior", desc: "7-day study streak", unlocked: true },
  { id: "firstAsk", title: "Curious Mind", desc: "Ask the AI Tutor 10 times", unlocked: true },
  { id: "physics50", title: "Force Field", desc: "50% Physics mastery", unlocked: true },
  { id: "perfect", title: "Perfect Paper", desc: "Score 100% on a quiz", unlocked: false },
  { id: "chem", title: "Bond Breaker", desc: "Finish Chemistry electrolysis lesson", unlocked: false },
  { id: "marathon", title: "Night Owl", desc: "Study 5 hours in a week", unlocked: false },
];
