import { randomInt } from "node:crypto"
import { Smsir } from "smsir-js"

// From the OS's CSPRNG: these codes are the second factor of the platform
// admin login as well as the shop owner's OTP, and Math.random is predictable.
function generateOtp(): string {
  return randomInt(100000, 1000000).toString()
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
