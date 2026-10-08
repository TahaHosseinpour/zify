"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ChoiceGroup } from "@/components/choice-group"
import { LEAD_STATUSES } from "@/lib/leads"

export function LeadControls({ id, status, adminNote }: { id: string; status: string; adminNote: string }) {
  const router = useRouter()
  const [currentStatus, setCurrentStatus] = useState(status)
  const [note, setNote] = useState(adminNote)
  const [saving, setSaving] = useState(false)

  async function save(patch: { status?: string; adminNote?: string }) {
    setSaving(true)
    try {
      const res = await fetch(`/api/admin/leads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? "خطا در ذخیره")
      router.refresh()
      return true
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در ذخیره")
      return false
    } finally {
      setSaving(false)
    }
  }

  async function handleStatus(next: string) {
    const previous = currentStatus
    setCurrentStatus(next)
    if (!(await save({ status: next }))) setCurrentStatus(previous)
  }

  return (
    <div className="flex w-full shrink-0 flex-col gap-2 lg:w-80">
      <ChoiceGroup
        aria-label="وضعیت درخواست"
        value={currentStatus}
        onChange={handleStatus}
        options={Object.entries(LEAD_STATUSES).map(([value, label]) => ({ value, label }))}
      />
      <Textarea
        rows={2}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="یادداشت پیگیری"
      />
      {note !== adminNote && (
        <Button
          size="sm"
          variant="outline"
          className="self-start"
          disabled={saving}
          onClick={async () => {
            if (await save({ adminNote: note })) toast.success("یادداشت ذخیره شد")
          }}
        >
          ذخیره‌ی یادداشت
        </Button>
      )}
    </div>
  )
}
