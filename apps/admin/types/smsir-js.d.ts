declare module "smsir-js" {
  interface VerifyParam {
    name: string
    value: string
  }

  class Smsir {
    constructor(apiKey: string, templateId: number)
    SendVerifyCode(
      mobile: string,
      templateId: number,
      parameters: VerifyParam[]
    ): Promise<unknown>
  }

  export { Smsir }
}
