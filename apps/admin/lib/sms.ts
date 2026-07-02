import { Smsir } from "smsir-js"

function generateOtp(): string {
  return Math.floor(100000 + Math.random() * 900000).toString()
}

export async function sendOtp(mobile: string): Promise<string> {
  const otp = generateOtp()

  if (process.env.SMS_MOCK === "true") {
    console.log(`[OTP] کد تأیید برای ${mobile}: ${otp}`)
    return otp
  }

  const sms = new Smsir(
    process.env.SMSIR_API_KEY!,
    Number(process.env.SMSIR_TEMPLATE_ID!)
  )

  await sms.SendVerifyCode(mobile, Number(process.env.SMSIR_TEMPLATE_ID!), [
    { name: "Code", value: otp },
  ])

  return otp
}
