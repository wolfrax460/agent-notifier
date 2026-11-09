import { Header } from "./components/Header";
import { Hero } from "./components/Hero";
import { NotificationStack } from "./components/NotificationStack";
import { HowItWorks } from "./components/HowItWorks";
import { Tools } from "./components/Tools";
import { ConnectTabs } from "./components/ConnectTabs";
import { WorksW } from "./components/WorksW";
import { Privacy } from "./components/Privacy";
import { Faq } from "./components/Faq";
import { Footer } from "./components/Footer";

export default function App() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        <NotificationStack />
        <HowItWorks />
        <Tools />
        <ConnectTabs />
        <WorksW />
        <Privacy />
        <Faq />
      </main>
      <Footer />
    </>
  );
}
