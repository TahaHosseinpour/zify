"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Edit01Icon, Delete01Icon } from "@hugeicons/core-free-icons"

interface FaqItem {
  id: string
  question: string
  answer: string
}

const emptyForm = { question: "", answer: "" }

export default function FaqPage() {
  const [items, setItems] = useState<FaqItem[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [editId, setEditId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    const res = await fetch("/api/faq")
    setItems(await res.json())
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  function openNew() { setForm(emptyForm); setEditId(null); setDialogOpen(true) }
  function openEdit(item: FaqItem) {
    setForm({ question: item.question, answer: item.answer })
    setEditId(item.id)
    setDialogOpen(true)
  }

  async function handleSave() {
    if (!form.question || !form.answer) { toast.error("سوال و پاسخ الزامی است"); return }
    setSaving(true)
    try {
      const res = await fetch(editId ? `/api/faq/${editId}` : "/api/faq", {
        method: editId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      })
      if (!res.ok) throw new Error()
      toast.success(editId ? "ویرایش شد" : "اضافه شد")
      setDialogOpen(false)
      load()
    } catch { toast.error("خطا") } finally { setSaving(false) }
  }

  async function handleDelete(id: string) {
    if (!confirm("حذف شود؟")) return
    await fetch(`/api/faq/${id}`, { method: "DELETE" })
    toast.success("حذف شد")
    load()
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <Button size="sm" onClick={openNew}>
          <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
          سوال جدید
        </Button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center text-muted-foreground">هنوز سوالی اضافه نشده</div>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((item, i) => (
            <motion.div key={item.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card>
                <CardContent className="flex items-start justify-between gap-4 p-4">
                  <div className="flex flex-col gap-1 flex-1 min-w-0">
                    <p className="font-medium text-sm">{item.question}</p>
                    <p className="text-sm text-muted-foreground line-clamp-2">{item.answer}</p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button size="icon-sm" variant="ghost" onClick={() => openEdit(item)}>
                      <HugeiconsIcon icon={Edit01Icon} />
                    </Button>
                    <Button size="icon-sm" variant="ghost" onClick={() => handleDelete(item.id)}>
                      <HugeiconsIcon icon={Delete01Icon} className="text-destructive" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent dir="rtl">
          <DialogHeader>
            <DialogTitle>{editId ? "ویرایش سوال" : "سوال جدید"}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>سوال *</Label>
              <Input value={form.question} onChange={(e) => setForm(f => ({ ...f, question: e.target.value }))} placeholder="مثال: روش ارسال چیست؟" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>پاسخ *</Label>
              <Textarea value={form.answer} onChange={(e) => setForm(f => ({ ...f, answer: e.target.value }))} rows={4} placeholder="پاسخ کامل را بنویسید..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>انصراف</Button>
            <Button onClick={handleSave} disabled={saving}>{saving ? "ذخیره..." : "ذخیره"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
