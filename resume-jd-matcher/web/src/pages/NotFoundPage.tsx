import { Briefcase } from 'lucide-react'
import { ButtonLink, EmptyState, PageHeader } from '../components/ui'
import { useDocumentTitle } from '../hooks'

export default function NotFoundPage() {
  useDocumentTitle('Page not found')
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState
        icon={Briefcase}
        title="There's nothing at this address"
        action={
          <ButtonLink to="/jobs" variant="primary">
            Go to jobs
          </ButtonLink>
        }
      >
        The link may be out of date. Start from the jobs list.
      </EmptyState>
    </>
  )
}
