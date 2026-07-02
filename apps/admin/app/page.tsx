import Navbar from "@/components/landing/Navbar"
import Footer from "@/components/landing/Footer"
import HeroSection from "@/components/landing/HeroSection"
import ModesSection from "@/components/landing/ModesSection"
import CapabilitiesSection from "@/components/landing/CapabilitiesSection"
import CtaSection from "@/components/landing/CtaSection"

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <HeroSection />
      <main className="bg-background">
        <ModesSection />
        <CapabilitiesSection />
        <CtaSection />
      </main>
      <Footer />
    </div>
  )
}
