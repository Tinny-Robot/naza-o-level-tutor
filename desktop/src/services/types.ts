/** Shared API response types (mirrors GenerationPipeline + static routes). */

export type Citation = {
  subject: string;
  topic: string;
  source: string;
  chunk_id: string;
  score: number;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatResponse = {
  type?: "chat";
  mode: "study" | "general";
  answer: string;
  citations: Citation[];
  confidence: number;
  retrieved_chunks: unknown[];
  refused: boolean;
  latency_ms: number;
};

export type ImageRef = {
  path?: string;
  url: string;
  caption?: string;
  page?: number | string | null;
};

export type LessonSectionStructured = {
  heading: string;
  body: string;
  diagram_placeholder?: string | null;
  diagram_svg?: string | null;
  image_refs?: ImageRef[];
};

export type WorkedExample = {
  problem: string;
  steps: string[];
  answer: string;
};

export type CheckUnderstanding = {
  question: string;
  expected_answer: string;
  hint: string;
};

export type PracticeItem = {
  question: string;
  options: string[] | null;
  correct_answer: string;
  explanation: string;
};

export type RevisionCardData = {
  front: string;
  back: string;
};

export type LessonResponse = {
  type: "lesson";
  title: string;
  introduction: string;
  objectives: string[];
  sections: LessonSectionStructured[];
  worked_example: WorkedExample;
  check_understanding: CheckUnderstanding;
  practice: PracticeItem;
  summary: string[];
  revision_card: RevisionCardData;
  citations: Citation[];
  image_refs?: ImageRef[];
  mode: "lesson";
  confidence: number;
  retrieved_chunks: unknown[];
  refused: boolean;
  answer: string;
  latency_ms?: number;
};

export type TutorResponse = ChatResponse | LessonResponse;

export type LessonFeedbackResponse = {
  type: "feedback";
  correct: boolean;
  feedback: string;
  encouragement: string;
};

export type LessonFeedbackRequest = {
  question: string;
  expected_answer: string;
  student_answer: string;
  explanation?: string | null;
  kind?: "check" | "practice";
  title?: string | null;
};

export type HealthResponse = {
  status: string;
  offline: boolean;
  model: string;
};

/** Static GET /lesson demo payload (separate from Tutor lesson JSON). */
export type LessonSection = {
  heading: string;
  body: string;
  kind?: string;
  options?: string[];
  answer?: string;
};

export type LessonPayload = {
  subject: string;
  topic: string;
  title: string;
  duration_min: number;
  sections: LessonSection[];
  summary: string[];
};

export type QuizOption = { key: string; text: string };

export type QuizPayload = {
  id: string;
  subject: string;
  prompt: string;
  options: QuizOption[];
  answer: string;
};

export type SubjectMastery = {
  id: string;
  name: string;
  mastery: number;
  color: string;
  topic: string;
};

export type ProgressPayload = {
  streak: number;
  xp_week: number;
  accuracy: number;
  heatmap: Array<{ day: number; value: number }>;
  subjects: SubjectMastery[];
  weak_topic: string;
};

export type RevisionPayload = {
  front: string;
  back: string;
  strength: number;
  next_review: string;
};

export function isLessonResponse(res: TutorResponse): res is LessonResponse {
  return (res as LessonResponse).type === "lesson";
}
