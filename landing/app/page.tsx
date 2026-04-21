import Navbar from "@/components/Navbar";
import ThreeBackground from "@/components/ThreeBackground";
import Hero from "@/components/Hero";
import ScrollStory from "@/components/ScrollStory";
import Features from "@/components/Features";
import EarlyAccess from "@/components/EarlyAccess";
import FinalCTA from "@/components/FinalCTA";
import Footer from "@/components/Footer";

export default function Home() {
  return (
    <>
      <ThreeBackground />
      <Navbar />
      <Hero />
      <ScrollStory />
      <Features />
      <EarlyAccess />
      <FinalCTA />
      <Footer />
    </>
  );
}
