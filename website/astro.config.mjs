import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { sanitizeAnalyticsProperties } from './src/analytics-privacy.mjs';

const posthogPublicToken = 'phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V';
const posthogScript = `!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture identify alias people.set people.set_once people.unset reset opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing onFeatureFlags getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey captureException startSessionRecording stopSessionRecording sessionRecordingStarted capturePerformance captureTraceFeedback captureTraceMetric startExceptionCapture stopExceptionCapture".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);posthog.init('${posthogPublicToken}',{api_host:'https://us.i.posthog.com',defaults:'2026-05-30',person_profiles:'identified_only',capture_pageview:true,capture_pageleave:true,autocapture:{dom_event_allowlist:['click'],element_allowlist:['a','button']},disable_session_recording:true,save_referrer:false,save_campaign_params:false,advanced_disable_flags:true,sanitize_properties:${sanitizeAnalyticsProperties.toString()}});`;
const structuredData = {
  '@context': 'https://schema.org',
  '@graph': [
    { '@type': 'SoftwareSourceCode', name: 'RefPot', description: 'Experimental alpha custom embedded engine with Python CRUD and transactions; not production-qualified.', url: 'https://refpot.modepot.io/', codeRepository: 'https://github.com/tugrulguner/refpot', programmingLanguage: ['C++', 'Python'], runtimePlatform: 'CPython 3.11–3.14 on Linux x86_64 and macOS arm64', license: 'https://spdx.org/licenses/MIT.html', isPartOf: { '@type': 'Organization', name: 'ModePot', url: 'https://modepot.io/' } },
    { '@type': 'WebSite', name: 'RefPot documentation', url: 'https://refpot.modepot.io/', inLanguage: 'en' },
  ],
};
export default defineConfig({
  site: 'https://refpot.modepot.io',
  vite: { preview: { strictPort: true }, server: { strictPort: true } },
  integrations: [starlight({
    title: 'RefPot',
    description: 'Experimental alpha custom embedded engine with Python CRUD and transactions; not production-qualified.',
    favicon: '/refpot-mark.svg?v=offwhite-1',
    social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/tugrulguner/refpot' }],
    customCss: ['./src/styles/custom.css'],
    components: { Header: './src/components/FamilyHeader.astro', PageTitle: './src/components/ProjectPageTitle.astro' },
    head: [
      { tag: 'script', attrs: {}, content: posthogScript },
      { tag: 'link', attrs: { rel: 'alternate', type: 'text/plain', href: '/llms.txt', title: 'RefPot summary for AI agents' } },
      { tag: 'meta', attrs: { property: 'og:image', content: 'https://refpot.modepot.io/social-card.png?v=public-info-1' } },
      { tag: 'meta', attrs: { property: 'og:image:width', content: '1200' } },
      { tag: 'meta', attrs: { property: 'og:image:height', content: '630' } },
      { tag: 'meta', attrs: { property: 'og:image:alt', content: 'RefPot experimental alpha: embedded native C++ database with Python CRUD and explicit transactions' } },
      { tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
      { tag: 'meta', attrs: { name: 'twitter:image', content: 'https://refpot.modepot.io/social-card.png?v=public-info-1' } },
      { tag: 'script', attrs: { type: 'application/ld+json' }, content: JSON.stringify(structuredData) },
    ],
    sidebar: [
      { label: 'Start', items: [{ slug: 'index', label: 'Overview' }, { slug: 'package', label: 'Quick start' }] },
      { label: 'Build', items: [{ slug: 'build/crud' }, { slug: 'build/transactions' }, { slug: 'build/persistence' }, { slug: 'build/errors' }] },
      { label: 'Reference', items: [{ slug: 'reference/api' }, { slug: 'package-contract', label: 'Package contract' }, { slug: 'reference/agent-guide' }] },
      { label: 'Internals', items: [{ slug: 'internals/recovery' }] },
      { label: 'Project', items: [{ slug: 'status' }, { slug: 'project/benchmarks' }, { slug: 'project/package-performance' }, { slug: 'project/contributing' }, { slug: 'design' }, { slug: 'performance-method' }, { slug: 'project/roadmap', label: 'Roadmap' }] },
    ],
  })],
});
