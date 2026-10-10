import { useState } from 'react'
import { Brain, Check, GitPullRequest, Sparkles, X } from 'lucide-react'
import { Badge, Button, Card, ConfirmDialog, EmptyState, useToast } from '../../components/ui'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import type { Json } from './types'

export default function AiGovernance({
  recommendations,
  officeId,
  reload,
}: {
  recommendations: Json[]
  officeId?: number
  reload: () => Promise<void>
}) {
  const { t } = useI18n()
  const toast = useToast()
  const [generating, setGenerating] = useState(false)
  const [retraining, setRetraining] = useState(false)
  const [confirmRetrain, setConfirmRetrain] = useState(false)
  const [decidingId, setDecidingId] = useState<number | null>(null)

  const generate = async () => {
    if (!officeId) return
    setGenerating(true)
    try {
      const result = await api.recommendations(officeId, true)
      toast.success(t('admin.aiGenerated', 'Recommendations ready'), t('admin.aiGeneratedBody', 'Generated {count} recommendation(s) for review.').replace('{count}', String(result.generated)))
      await reload()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setGenerating(false)
    }
  }

  const retrain = async () => {
    setConfirmRetrain(false)
    setRetraining(true)
    try {
      const result = await api.retrain()
      toast.success(t('admin.aiRetrained', 'Model retraining started'), t('admin.aiRetrainedBody', 'Retrained {count} model(s).').replace('{count}', String(result.trained)))
      await reload()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setRetraining(false)
    }
  }

  const decide = async (id: number, status: 'ACCEPTED' | 'REJECTED') => {
    setDecidingId(id)
    try {
      await api.decideRecommendation(id, status)
      toast.success(status === 'ACCEPTED' ? t('admin.aiAccepted', 'Recommendation accepted') : t('admin.aiDismissed', 'Recommendation dismissed'))
      await reload()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setDecidingId(null)
    }
  }

  return (
    <>
      <Card
        kicker={t('admin.ai', 'AI governance')}
        title={t('admin.aiTitle', 'Counter recommendations')}
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => void generate()} loading={generating} icon={<GitPullRequest size={15} />}>
              {t('admin.aiGenerate', 'Generate recommendations')}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setConfirmRetrain(true)} loading={retraining} icon={<Brain size={15} />}>
              {t('admin.aiRetrain', 'Retrain model')}
            </Button>
          </div>
        }
      >
        <p className="text-[13px] text-ink-2 mt-0 mb-4">{t('admin.aiHint', 'Review AI scheduling recommendations before they are applied.')}</p>

        {recommendations.length === 0 ? (
          <EmptyState
            icon={<Sparkles size={22} />}
            title={t('admin.aiEmptyTitle', 'No recommendations right now')}
            hint={t('admin.aiEmpty', 'No recommendations right now. Generate some to review.')}
            action={
              <Button size="sm" onClick={() => void generate()} loading={generating} icon={<GitPullRequest size={15} />}>
                {t('admin.aiGenerate', 'Generate recommendations')}
              </Button>
            }
          />
        ) : (
          <ul className="m-0 p-0 list-none flex flex-col gap-3">
            {recommendations.map((rec) => (
              <li key={String(rec.id)} className="rounded-md border border-line p-4 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="m-0 text-[15px] font-semibold text-ink">{String(rec.title)}</p>
                  <p className="m-0 mt-1 text-[13px] text-ink-2">
                    {t('admin.expectedReduction', 'Expected reduction ≈ {min} min').replace('{min}', String(rec.expected_reduction_min))}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" loading={decidingId === Number(rec.id)} onClick={() => void decide(Number(rec.id), 'ACCEPTED')} icon={<Check size={15} />}>
                    {t('admin.aiAccept', 'Accept')}
                  </Button>
                  <Button variant="secondary" size="sm" disabled={decidingId === Number(rec.id)} onClick={() => void decide(Number(rec.id), 'REJECTED')} icon={<X size={15} />}>
                    {t('admin.aiReject', 'Dismiss')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="text-[12px] text-ink-3 mt-3 flex items-center gap-2 m-0">
        <Badge tone="info">{t('admin.humanInLoop', 'Human in the loop')}</Badge>
        {t('admin.aiSafety', 'Recommendations only change counters after you accept them. Nothing is applied automatically.')}
      </p>

      <ConfirmDialog
        open={confirmRetrain}
        onClose={() => setConfirmRetrain(false)}
        onConfirm={() => void retrain()}
        title={t('admin.aiRetrain', 'Retrain model')}
        body={t('admin.aiRetrainConfirm', 'Retrain the forecasting model with the latest data? This can take a few minutes and uses extra resources.')}
        confirmLabel={t('admin.aiRetrainConfirmBtn', 'Retrain now')}
      />
    </>
  )
}
