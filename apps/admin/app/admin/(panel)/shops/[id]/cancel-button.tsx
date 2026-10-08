"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

export function CancelSubscriptionButton({ subscriptionId }: { subscriptionId: string }) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [working, setWorking] = useState(false)

  async function handleCancel() {
    setWorking(true)
    try {
      const res = await fetch(`/api/admin/subscriptions/${subscriptionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "cancelled" }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? "خطا در لغو اشتراک")
      toast.success("اشتراک لغو شد")
      setOpen(false)
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در لغو اشتراک")
    } finally {
      setWorking(false)
    }
  }

  return (
    <>
      <Button variant="outline" size="sm" className="self-start text-destructive" onClick={() => setOpen(true)}>
        لغو اشتراک
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent dir="rtl">
          <AlertDialogHeader>
            <AlertDialogTitle>این اشتراک لغو شود؟</AlertDialogTitle>
            <AlertDialogDescription>
              دستیار این فروشگاه از همین حالا خاموش می‌شود و به مشتری‌ها پاسخ نمی‌دهد. سابقه‌ی اشتراک حذف نمی‌شود.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>انصراف</AlertDialogCancel>
            <AlertDialogAction onClick={handleCancel} disabled={working}>
              {working ? "در حال لغو..." : "لغو اشتراک"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
