import Script from "next/script";

export const metadata = { title: "Ask BU AI button – website demo" };

/** A fictional sample university page showing how the one-line "Ask BU AI" launcher looks on a website. */
export default function WebsiteDemo() {
  return (
    <div className="demo-site">
      <p className="demo-note">
        Sample page for the demo (fictional “Example University”). On a real site, the button in the corner is added with one line of code:{" "}
        <code>{'<script src="https://YOUR-BU-AI-HOST/embed.js" defer></script>'}</code>
      </p>
      <header className="demo-top">
        <span className="demo-logo" aria-hidden="true">E</span>
        <span className="demo-name">Example University</span>
        <nav className="demo-nav" aria-label="Example navigation">
          <span>Admissions</span><span>Academics</span><span>Student life</span><span>Financial aid</span><span>About</span>
        </nav>
      </header>
      <main>
        <section className="demo-hero">
          <p className="demo-kicker">Fall 2027 applications are open</p>
          <h1>Learn here. Lead anywhere.</h1>
          <p>Undergraduate, graduate and online programs built around you.</p>
          <span className="demo-btn">Apply now</span><span className="demo-btn ghost">Plan a visit</span>
        </section>
        <div className="demo-body">
          <div className="demo-cards">
            <div><b>Admissions</b><p>Requirements, deadlines and how to apply.</p><span>Learn more →</span></div>
            <div><b>Academics</b><p>Programs, calendars and academic support.</p><span>Explore →</span></div>
            <div><b>Student life</b><p>Housing, dining, clubs and campus events.</p><span>Discover →</span></div>
          </div>
          <div className="demo-news">
            <b>News &amp; events</b>
            <div><span>Nov 20</span>Library extends evening hours for finals week</div>
            <div><span>Dec 1</span>Early acceptance deadline for first-year applicants</div>
            <div><span>Jan 12</span>Spring term classes begin</div>
          </div>
        </div>
      </main>
      <Script src="/embed.js" strategy="afterInteractive" />
    </div>
  );
}
