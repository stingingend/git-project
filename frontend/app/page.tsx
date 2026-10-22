import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Braces,
  GitBranch,
  Github,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import "./marketing.css";

const features = [
  {
    icon: Network,
    number: "01",
    title: "See the connections.",
    text: "Explore imports, symbols, and candidate calls in an interactive map. Follow a dependency straight to its source.",
  },
  {
    icon: Search,
    number: "02",
    title: "Find the meaning.",
    text: "Search by name or intent. Ask questions and get source findings with citations you can actually inspect.",
  },
  {
    icon: GitBranch,
    number: "03",
    title: "Understand the change.",
    text: "Trace potential impact, inspect architecture, and review public pull requests with the codebase in context.",
  },
];

function RepositoryMap() {
  return (
    <div
      className="product-preview"
      aria-label="Illustration of a Python repository dependency map"
    >
      <div className="preview-toolbar">
        <span>
          <span className="live-dot" /> Repository explorer
        </span>
        <span className="preview-tag">Illustrative workspace</span>
      </div>
      <div className="preview-body">
        <div className="preview-tree">
          <div>EXPLORER</div>
          <p>
            <GitBranch size={14} /> acme / toolkit
          </p>
          <span>⌄ &nbsp; src / toolkit</span>
          <span className="tree-current">&nbsp;&nbsp; __init__.py</span>
          <span>&nbsp;&nbsp; serializer.py</span>
          <span>&nbsp;&nbsp; signer.py</span>
          <span>&nbsp;&nbsp; encoding.py</span>
          <span>› &nbsp; tests</span>
          <span> &nbsp; pyproject.toml</span>
          <div className="tree-bottom">
            <span className="live-dot" /> Source connected
          </div>
        </div>
        <div className="preview-map">
          <div className="map-label">
            <Network size={14} /> Dependency map{" "}
            <span>4 files · 3 connections</span>
          </div>
          <svg
            viewBox="0 0 560 330"
            role="img"
            aria-label="The package imports serializer, which imports signer and encoding."
          >
            <defs>
              <pattern
                id="map-dots"
                width="20"
                height="20"
                patternUnits="userSpaceOnUse"
              >
                <circle cx="1" cy="1" r="1" fill="#d8dce8" />
              </pattern>
              <linearGradient id="line-glow">
                <stop stopColor="#c5b9f9" />
                <stop offset="1" stopColor="#7762e4" />
              </linearGradient>
            </defs>
            <rect width="560" height="330" fill="url(#map-dots)" />
            <g fill="none" stroke="url(#line-glow)" strokeWidth="2">
              <path
                className="map-wire"
                d="M 140 165 C 185 165 170 105 225 105"
              />
              <path
                className="map-wire"
                d="M 345 105 C 395 105 355 220 410 220"
              />
              <path
                className="map-wire"
                d="M 285 128 C 285 180 220 170 220 220"
              />
            </g>
            {[
              [30, 143, "__init__.py"],
              [225, 83, "serializer.py"],
              [160, 220, "encoding.py"],
              [390, 220, "signer.py"],
            ].map(([x, y, label], i) => (
              <g
                key={label}
                className={`map-node map-node-${i}`}
                transform={`translate(${x} ${y})`}
              >
                <rect
                  width="130"
                  height="46"
                  rx="10"
                  fill={i === 1 ? "#ede9ff" : "white"}
                  stroke={i === 1 ? "#9e8be9" : "#d9deea"}
                />
                <text
                  x="15"
                  y="29"
                  fontSize="12"
                  fontFamily="monospace"
                  fill={i === 1 ? "#6147c1" : "#4e5d76"}
                >
                  {label}
                </text>
              </g>
            ))}
          </svg>
          <div className="map-caption">
            <span>
              <i /> Python module
            </span>
            <span>→ &nbsp; Import relationship</span>
            <span>Explore the structure ↗</span>
          </div>
        </div>
      </div>
      <div className="preview-question">
        <Sparkles size={17} />
        <span>Where does serialization happen?</span>
        <span className="question-shortcut">
          Search the codebase <ArrowRight size={14} />
        </span>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="marketing">
      <header className="site-header">
        <Link href="/" className="site-brand">
          <span>
            <Braces size={22} />
          </span>
          CodeAtlas
        </Link>
        <nav aria-label="Main navigation">
          <a href="#features">Product</a>
          <a href="#workflow">How it works</a>
          <a
            href="https://github.com/stingingend/git-project"
            target="_blank"
            rel="noreferrer"
          >
            GitHub <ArrowUpRight size={13} />
          </a>
        </nav>
        <Link className="nav-cta" href="/workspace">
          Open workspace <ArrowUpRight size={15} />
        </Link>
      </header>
      <main>
        <section className="landing-hero">
          <div className="hero-pill">
            <span className="live-dot" /> A clearer view of your codebase
          </div>
          <h1>
            Less searching.
            <br />
            More <span>understanding.</span>
          </h1>
          <p className="hero-copy">
            Turn a GitHub repository into a connected map of code.
            <br className="desktop-break" /> Explore the structure, find
            answers, and see what a change could touch.
          </p>
          <div className="hero-actions">
            <Link className="landing-primary" href="/workspace">
              Explore your repository <ArrowRight size={17} />
            </Link>
            <a
              className="landing-secondary"
              href="https://github.com/stingingend/git-project"
              target="_blank"
              rel="noreferrer"
            >
              <Github size={17} /> View the source
            </a>
          </div>
          <div className="hero-notes">
            <span>
              <ShieldCheck size={14} /> Python · JavaScript · TypeScript
            </span>
            <span>
              <Braces size={14} /> Source-backed insights
            </span>
          </div>
          <RepositoryMap />
        </section>
        <section className="landing-features" id="features">
          <div className="section-kicker">FROM FILES TO THE BIG PICTURE</div>
          <h2>
            The context your editor
            <br />
            doesn’t give you.
          </h2>
          <div className="feature-grid">
            {features.map(({ icon: Icon, number, title, text }) => (
              <article key={number}>
                <div className="feature-top">
                  <span>
                    <Icon size={21} />
                  </span>
                  <small>{number}</small>
                </div>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="landing-workflow" id="workflow">
          <div>
            <div className="section-kicker">BUILT AROUND YOUR CODE</div>
            <h2>
              A new repository.
              <br />A familiar starting point.
            </h2>
            <p>
              Move from an unfamiliar project to the files that matter, with the
              original source always one click away.
            </p>
            <Link href="/workspace">
              Start exploring <ArrowRight size={16} />
            </Link>
          </div>
          <ol>
            {[
              [
                "Connect",
                "Paste a public GitHub repository URL. CodeAtlas collects its supported source without running it.",
              ],
              [
                "Map",
                "Index definitions and relationships, then explore files in a connected workspace.",
              ],
              [
                "Investigate",
                "Search symbols, trace dependencies, or build a semantic index for source-cited questions.",
              ],
            ].map(([title, text], i) => (
              <li key={title}>
                <span>0{i + 1}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <section className="landing-close">
          <div className="section-kicker">MAKE SENSE OF WHAT’S NEXT</div>
          <h2>
            Your code has a story.
            <br />
            See how it connects.
          </h2>
          <Link className="landing-primary" href="/workspace">
            Open your workspace <ArrowRight size={17} />
          </Link>
          <p>A personal workspace for exploring public repositories.</p>
        </section>
      </main>
      <footer className="site-footer">
        <Link href="/" className="site-brand">
          <Braces size={21} />
          CodeAtlas
        </Link>
        <span>Find your way through the code.</span>
        <a href="https://github.com/stingingend/git-project">
          Source on GitHub <ArrowUpRight size={14} />
        </a>
      </footer>
    </div>
  );
}
