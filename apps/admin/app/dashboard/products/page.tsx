"use client"

import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { toast } from "sonner"
import { HugeiconsIcon } from "@hugeicons/react"
import { Add01Icon, Edit01Icon, Delete01Icon, FileImportIcon, Download04Icon } from "@hugeicons/core-free-icons"
import Papa from "papaparse"
import * as XLSX from "xlsx"

interface Product {
  id: string
  name: string
  price: number
  imageUrl: string | null
  isActive: boolean
  productUrl: string | null
  description: string | null
  category: string | null
  brand: string | null
}

const emptyForm = {
  name: "",
  price: "",
  imageUrl: "",
  productUrl: "",
  description: "",
  category: "",
  brand: "",
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [editId, setEditId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const bulkFileRef = useRef<HTMLInputElement>(null)

  // Offered as autocomplete so the same category keeps the same spelling. The
  // agent matches this column exactly, so "کفش ورزشی" and "کفش‌ورزشی" would be
  // two different categories and each would only find half the catalog.
  const categorySuggestions = Array.from(
    new Set(products.map((p) => p.category).filter((c): c is string => Boolean(c)))
  ).sort()

  async function load() {
    setLoading(true)
    const res = await fetch("/api/products")
    const data = await res.json()
    setProducts(data)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  function openNew() {
    setForm(emptyForm)
    setEditId(null)
    setDialogOpen(true)
  }

  function openEdit(p: Product) {
    setForm({
      name: p.name,
      price: String(p.price),
      imageUrl: p.imageUrl ?? "",
      productUrl: p.productUrl ?? "",
      description: p.description ?? "",
      category: p.category ?? "",
      brand: p.brand ?? "",
    })
    setEditId(p.id)
    setDialogOpen(true)
  }

  async function handleSave() {
    if (!form.name || !form.price) { toast.error("نام و قیمت الزامی است"); return }
    setSaving(true)
    try {
      const body = { ...form, price: Number(form.price) }
      const res = await fetch(editId ? `/api/products/${editId}` : "/api/products", {
        method: editId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error()
      toast.success(editId ? "محصول ویرایش شد" : "محصول اضافه شد")
      setDialogOpen(false)
      load()
    } catch {
      toast.error("خطا در ذخیره محصول")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("آیا مطمئنید؟")) return
    await fetch(`/api/products/${id}`, { method: "DELETE" })
    toast.success("محصول حذف شد")
    load()
  }

  function downloadSample() {
    const rows = [
      ["نام", "قیمت", "دسته", "برند", "توضیحات", "لینک تصویر", "لینک محصول"],
      ["کفش ورزشی نایک", "1200000", "کفش ورزشی", "Nike", "کفش ورزشی مناسب پیاده‌روی و دویدن", "https://example.com/image.jpg", "https://example.com/product"],
    ]
    const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n")
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "نمونه-محصولات.csv"
    a.click()
    URL.revokeObjectURL(url)
  }

  async function importRows(rows: Record<string, string>[]) {
    setImporting(true)
    let ok = 0
    for (const row of rows) {
      try {
        const res = await fetch("/api/products", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: row.name || row["نام"],
            price: Number(row.price || row["قیمت"] || 0),
            description: row.description || row["توضیحات"] || "",
            productUrl: row.url || row["لینک محصول"] || row["لینک"] || "",
            imageUrl: row.image || row["لینک تصویر"] || row["تصویر"] || "",
            category: row.category || row["دسته"] || row["دسته‌بندی"] || "",
            brand: row.brand || row["برند"] || "",
          }),
        })
        if (res.ok) ok++
      } catch {}
    }
    toast.success(`${ok.toLocaleString("fa-IR")} محصول وارد شد`)
    setImporting(false)
    setBulkOpen(false)
    load()
    if (bulkFileRef.current) bulkFileRef.current.value = ""
  }

  function handleBulkFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (/\.xlsx?$/i.test(file.name)) {
      const reader = new FileReader()
      reader.onload = (ev) => {
        const data = new Uint8Array(ev.target?.result as ArrayBuffer)
        const workbook = XLSX.read(data, { type: "array" })
        const sheet = workbook.Sheets[workbook.SheetNames[0]]
        importRows(XLSX.utils.sheet_to_json(sheet) as Record<string, string>[])
      }
      reader.readAsArrayBuffer(file)
    } else {
      Papa.parse(file, {
        header: true,
        skipEmptyLines: true,
        complete: (result) => importRows(result.data as Record<string, string>[]),
      })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setBulkOpen(true)}>
            <HugeiconsIcon icon={FileImportIcon} data-icon="inline-start" />
            وارد کردن گروهی
          </Button>
          <Button size="sm" onClick={openNew}>
            <HugeiconsIcon icon={Add01Icon} data-icon="inline-start" />
            محصول جدید
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex flex-col gap-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
            </div>
          ) : products.length === 0 ? (
            <div className="py-16 text-center text-muted-foreground">
              <p>هنوز محصولی اضافه نشده</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead></TableHead>
                  <TableHead>نام</TableHead>
                  <TableHead>قیمت</TableHead>
                  <TableHead>وضعیت</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {products.map((p, i) => (
                  <motion.tr
                    key={p.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="border-b last:border-0"
                  >
                    <TableCell>
                      {p.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={p.imageUrl} alt={p.name} className="size-10 rounded-md object-cover" />
                      ) : (
                        <div className="size-10 rounded-md bg-muted" />
                      )}
                    </TableCell>
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell>{Number(p.price).toLocaleString("fa-IR")} تومان</TableCell>
                    <TableCell>
                      <Badge variant={p.isActive ? "default" : "secondary"}>
                        {p.isActive ? "فعال" : "غیرفعال"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 justify-end">
                        <Button size="icon-sm" variant="ghost" onClick={() => openEdit(p)}>
                          <HugeiconsIcon icon={Edit01Icon} />
                        </Button>
                        <Button size="icon-sm" variant="ghost" onClick={() => handleDelete(p.id)}>
                          <HugeiconsIcon icon={Delete01Icon} className="text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </motion.tr>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent dir="rtl">
          <DialogHeader>
            <DialogTitle>{editId ? "ویرایش محصول" : "محصول جدید"}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>نام محصول *</Label>
              <Input value={form.name} onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))} placeholder="مثال: کفش ورزشی نایک" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>قیمت (تومان) *</Label>
              <Input type="number" dir="ltr" value={form.price} onChange={(e) => setForm(f => ({ ...f, price: e.target.value }))} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>لینک تصویر</Label>
              <Input dir="ltr" value={form.imageUrl} onChange={(e) => setForm(f => ({ ...f, imageUrl: e.target.value }))} placeholder="https://..." />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>لینک محصول</Label>
              <Input dir="ltr" value={form.productUrl} onChange={(e) => setForm(f => ({ ...f, productUrl: e.target.value }))} placeholder="https://..." />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>دسته‌بندی</Label>
              <Input
                list="category-suggestions"
                value={form.category}
                onChange={(e) => setForm(f => ({ ...f, category: e.target.value }))}
                placeholder="مثال: کفش ورزشی"
              />
              <datalist id="category-suggestions">
                {categorySuggestions.map((c) => <option key={c} value={c} />)}
              </datalist>
              <p className="text-xs text-muted-foreground">
                دستیار برای فیلتر کردن دقیق محصولات از این استفاده می‌کند. دسته‌های یکسان را
                با همین املا تکرار کنید.
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>برند</Label>
              <Input value={form.brand} onChange={(e) => setForm(f => ({ ...f, brand: e.target.value }))} placeholder="مثال: Nike" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>توضیحات</Label>
              <Textarea value={form.description} onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))} rows={3} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>انصراف</Button>
            <Button onClick={handleSave} disabled={saving}>{saving ? "در حال ذخیره..." : "ذخیره"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
        <DialogContent dir="rtl">
          <DialogHeader>
            <DialogTitle>وارد کردن گروهی محصولات</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <button
              type="button"
              onClick={downloadSample}
              className="flex items-center justify-between gap-3 rounded-md border border-dashed border-input p-3 text-right hover:bg-accent transition-colors"
            >
              <div>
                <p className="text-sm font-medium">دانلود فایل نمونه</p>
                <p className="text-xs text-muted-foreground">ستون‌های مورد نیاز را از این فایل ببینید</p>
              </div>
              <HugeiconsIcon icon={Download04Icon} className="text-primary shrink-0" />
            </button>

            <div className="flex flex-col gap-1.5">
              <Label>فایل CSV یا اکسل</Label>
              <input
                ref={bulkFileRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                disabled={importing}
                onChange={handleBulkFile}
                className="text-sm file:me-3 file:h-8 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:text-sm file:font-medium file:text-secondary-foreground disabled:opacity-50"
              />
              <p className="text-xs text-muted-foreground">
                {importing ? "در حال وارد کردن محصولات..." : "فایل .csv یا .xlsx با ستون‌های نام، قیمت، دسته، برند، توضیحات، لینک تصویر و لینک محصول"}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkOpen(false)} disabled={importing}>بستن</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
