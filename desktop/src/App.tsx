import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ErrorBoundary } from "./components/layout/ErrorBoundary";
import { ExamsPage } from "./features/exams/ExamsPage";
import { HomePage } from "./features/home/HomePage";
import { LearnPage } from "./features/learn/LearnPage";
import { PracticePage } from "./features/practice/PracticePage";
import { ProgressPage } from "./features/progress/ProgressPage";
import { TutorPage } from "./features/tutor/TutorPage";
import { LanguageProvider } from "./i18n/LanguageProvider";

/** HashRouter avoids HTTP 404 on deep links behind port-forward proxies. */
export default function App() {
  return (
    <LanguageProvider>
      <ErrorBoundary>
        <HashRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              <Route path="learn" element={<LearnPage />} />
              <Route path="learn/:courseId" element={<LearnPage />} />
              <Route path="tutor" element={<TutorPage />} />
              <Route path="practice" element={<PracticePage />} />
              <Route path="exams" element={<ExamsPage />} />
              <Route path="progress" element={<ProgressPage />} />
              {/* Legacy routes → Home */}
              <Route path="quiz" element={<Navigate to="/exams" replace />} />
              <Route path="lesson" element={<Navigate to="/learn" replace />} />
              <Route path="revision" element={<Navigate to="/progress" replace />} />
              <Route path="achievements" element={<Navigate to="/" replace />} />
              <Route path="profile" element={<Navigate to="/" replace />} />
              <Route path="settings" element={<Navigate to="/" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </HashRouter>
      </ErrorBoundary>
    </LanguageProvider>
  );
}
