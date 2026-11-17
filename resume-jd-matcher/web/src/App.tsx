import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AnnotatePage from './pages/AnnotatePage'
import CandidatePage from './pages/CandidatePage'
import CandidatesPage from './pages/CandidatesPage'
import ComparePage from './pages/ComparePage'
import EvaluatePage from './pages/EvaluatePage'
import ExtractPage from './pages/ExtractPage'
import JobDetailPage from './pages/JobDetailPage'
import JobsPage from './pages/JobsPage'
import NotFoundPage from './pages/NotFoundPage'
import ReportPage from './pages/ReportPage'
import SettingsPage from './pages/SettingsPage'
import ShortlistPage from './pages/ShortlistPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/jobs" replace />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="jobs/:jobId" element={<JobDetailPage />} />
        <Route path="jobs/:jobId/compare" element={<ComparePage />} />
        <Route path="jobs/:jobId/shortlist" element={<ShortlistPage />} />
        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="candidates/:resumeId" element={<CandidatePage />} />
        <Route path="report/:jobId/:resumeId" element={<ReportPage />} />
        <Route path="extract" element={<ExtractPage />} />
        <Route path="evaluate" element={<EvaluatePage />} />
        <Route path="evaluate/annotate" element={<AnnotatePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
