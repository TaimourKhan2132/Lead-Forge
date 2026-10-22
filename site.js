// LeadForge: the live page. Everything here is an enhancement; the page reads fully without it.
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const watch = 'IntersectionObserver' in window;
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const wait = ms => new Promise(done => setTimeout(done, ms));
  const once = (element, options, run) => {
    if (!watch) return run();
    const seen = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { seen.disconnect(); run(); }
    }, options);
    seen.observe(element);
  };

  // Sections ease in as they are reached.
  $$('.reveal').forEach(element => {
    if (calm) return element.classList.add('in');
    once(element, { rootMargin: '0px 0px -8% 0px', threshold: .06 }, () => element.classList.add('in'));
  });

  // The headline numbers count up once.
  if (!calm) $$('[data-count]').forEach(element => once(element, { threshold: .6 }, () => {
    const end = Number(element.dataset.count), began = performance.now();
    const step = now => {
      const part = Math.min(1, (now - began) / 900);
      element.textContent = Math.round(end * (1 - Math.pow(1 - part, 3)));
      if (part < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }));

  // The nav shows which section is on screen.
  const links = new Map($$('.nav nav a').map(link => [link.getAttribute('href').slice(1), link]));
  if (watch) {
    const here = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      links.forEach(link => link.removeAttribute('aria-current'));
      links.get(entry.target.id).setAttribute('aria-current', 'true');
    }), { rootMargin: '-45% 0px -50% 0px' });
    links.forEach((_, id) => { const section = document.getElementById(id); if (section) here.observe(section); });
  }

  // Tabs: the email, its two follow-ups and the LinkedIn note.
  $$('[role=tablist]').forEach(list => {
    const tabs = $$('[role=tab]', list);
    const select = (tab, focus) => {
      tabs.forEach(other => {
        const on = other === tab;
        other.setAttribute('aria-selected', on);
        other.tabIndex = on ? 0 : -1;
        document.getElementById(other.getAttribute('aria-controls')).hidden = !on;
      });
      if (focus) tab.focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(tab));
      tab.addEventListener('keydown', event => {
        const move = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (!move) return;
        event.preventDefault();
        select(tabs[(index + move + tabs.length) % tabs.length], true);
      });
    });
    select(tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0]);
  });

  // A line in the email lights up the checks it depends on, and the other way round.
  $$('[data-picks]').forEach(scope => {
    const items = $$('[data-pick]', scope);
    const light = id => items.forEach(item => item.classList.toggle('on', item.dataset.pick === id));
    items.forEach(item => ['mouseenter', 'focus', 'click'].forEach(type =>
      item.addEventListener(type, () => light(item.dataset.pick))));
    light('1');
  });

  // How a claim survives: six invented cases, walked through the gates verify.py applies.
  const lab = $('[data-lab]');
  if (lab) {
    const listed = 'The listing opens, and the name on it matches.';
    const CASES = [
      { steps: [
          ['pass', 'It is on the list, as no_site.'],
          ['pass', listed],
          ['skip', 'Not needed: the claim is about the listing, so no site is opened.'],
          ['skip', 'Not needed.'],
          ['pass', 'There is still no Website button today.'],
          ['skip', 'Not needed: one look at the listing is enough.']],
        verdict: 'Kept. An email may say <q>no website on its Google listing</q>, and its check list carries the Google Maps link.' },
      { steps: [
          ['pass', 'It is on the list, as stale: a footer year of 2023 or older.'],
          ['pass', listed],
          ['pass', 'The page loads. No browser check, no consent banner.'],
          ['pass', 'The browser ends on the domain the listing gives.'],
          ['pass', 'The newest year beside the copyright mark is 2018.'],
          ['skip', 'Not needed: the year is there to be seen.']],
        verdict: 'Kept. An email may say <q>footer still says 2018</q>.' },
      { steps: [
          ['pass', 'It is on the list, as no_ads_tags.'],
          ['pass', listed],
          ['pass', 'The page loads. No browser check, no consent banner.'],
          ['pass', 'The browser ends on the domain the listing gives.'],
          ['pass', 'After 8 seconds: no dataLayer, gtag or fbq, no tag script, no tag request.'],
          ['pass', 'A second visit gives the same answer.']],
        verdict: 'Kept. An email may say <q>no Google tag or Meta Pixel on its site</q>. It is still the weakest of the seven, so emails prefer the others.' },
      { steps: [
          ['pass', 'It is on the list, as no_ads_tags.'],
          ['pass', listed],
          ['fail', 'A consent tool can hold tags back until someone clicks. The page counts as unread.']],
        verdict: 'Dropped. Nothing is said about this site’s tags, in either direction.' },
      { steps: [
          ['pass', 'It is on the list, as not_https.'],
          ['pass', listed],
          ['pass', 'A page loads.'],
          ['fail', 'The link lands on a different company’s domain. Whatever that page shows, it is not this business’s site.']],
        verdict: 'Dropped. Nothing is said about the page the link lands on.' },
      { steps: [
          ['fail', 'Retired on 2026-10-11. A page scan cannot see a button that opens another site.']],
        verdict: 'Refused. It never reaches a browser, and the linter rejects the wording in any draft.' },
    ];
    const gates = $$('.gate', lab), cases = $$('.case', lab), verdict = $('.verdict', lab);
    const end = gates[gates.length - 1];
    let turn = 0;
    const play = async index => {
      const mine = ++turn, chosen = CASES[index];
      cases.forEach((button, n) => button.setAttribute('aria-pressed', n === index));
      gates.forEach(gate => {
        gate.classList.remove('is-pass', 'is-skip', 'is-fail', 'is-kept');
        gate.classList.add('is-wait');
        const out = $('.out', gate);
        if (out) out.textContent = '';
      });
      verdict.className = 'verdict';
      verdict.textContent = '';
      let failed = false;
      for (let n = 0; n < chosen.steps.length; n++) {
        const [state, text] = chosen.steps[n];
        if (!calm) await wait(state === 'skip' ? 240 : 560);
        if (mine !== turn) return;
        gates[n].classList.replace('is-wait', `is-${state}`);
        $('.out', gates[n]).textContent = text;
        if (state === 'fail') { failed = true; break; }
      }
      if (!calm) await wait(420);
      if (mine !== turn) return;
      if (!failed) end.classList.replace('is-wait', 'is-kept');
      verdict.classList.add(failed ? 'dropped' : 'kept');
      verdict.innerHTML = chosen.verdict;
    };
    cases.forEach((button, index) => button.addEventListener('click', () => {
      play(index);
      // On a narrow screen the gates sit below the list of cases, so bring them into view.
      if (innerWidth <= 1040) $('.run', lab).scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
    }));
    once(lab, { threshold: .2 }, () => play(0));
  }

  // The terminal types its one command, then prints what the linter really said.
  $$('[data-term]').forEach(term => {
    const lines = $$('.ln', term), replay = $('.replay', term);
    if (!lines.length || calm) return;
    let turn = 0;
    const play = async () => {
      const mine = ++turn;
      term.classList.add('playing');
      lines.forEach(line => line.classList.remove('shown'));
      for (const line of lines) {
        const command = $('.cmd', line);
        if (command) {
          const full = command.dataset.full || (command.dataset.full = command.textContent);
          command.textContent = '';
          command.classList.add('typing');
          line.classList.add('shown');
          await wait(500);
          for (let n = 1; n <= full.length; n++) {
            if (mine !== turn) { command.textContent = full; return; }
            command.textContent = full.slice(0, n);
            await wait(16);
          }
          await wait(420);
          command.classList.remove('typing');
        } else {
          await wait(95);
          if (mine !== turn) return;
          line.classList.add('shown');
        }
      }
      term.classList.remove('playing');
    };
    if (replay) { replay.hidden = false; replay.addEventListener('click', play); }
    once(term, { threshold: .5 }, play);
  });

  // Copy the commands without their prompts and comments.
  $$('.copy').forEach(button => {
    if (!navigator.clipboard) return;
    button.hidden = false;
    button.addEventListener('click', async () => {
      const text = $(button.dataset.copy).innerText.split('\n')
        .map(line => line.trim()).filter(line => line && !line.startsWith('#'))
        .map(line => line.replace(/^\$ /, '')).join('\n');
      try { await navigator.clipboard.writeText(text); button.textContent = 'Copied'; }
      catch (error) { button.textContent = 'Select and copy'; }
      setTimeout(() => { button.textContent = 'Copy'; }, 1600);
    });
  });
})();
