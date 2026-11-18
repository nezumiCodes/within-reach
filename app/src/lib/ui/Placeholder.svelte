<script lang="ts">
  import { onMount } from 'svelte'
  import { formatRelease, loadRelease, type ReleaseInfo } from '../data/release'

  let release: ReleaseInfo | null = $state(null)

  onMount(async () => {
    release = await loadRelease()
  })
</script>

<main>
  <h1>Within Reach</h1>
  <p class="lede">
    A tool to find the nearest suitable pharmacies for a postcode in England, Scotland and Wales.
  </p>
  <p>This site is being built. Nothing here works yet.</p>

  <h2>Privacy by design</h2>
  <p>
    When it's ready, every search will run inside your browser. Postcodes and client details are
    never sent to any server, and this site sets no cookies and uses no analytics.
  </p>

  <footer>
    {#if release}
      <p>Data release: {formatRelease(release.release)}</p>
    {/if}
    <p>
      Will contain public sector information licensed under the Open Government Licence v3.0, and
      data © OpenStreetMap contributors (ODbL).
    </p>
  </footer>
</main>

<style>
  main {
    max-width: 40rem;
    margin: 0 auto;
    padding: 3rem 1.25rem;
  }
  .lede {
    font-size: 1.25rem;
  }
  footer {
    margin-top: 3rem;
    font-size: 0.875rem;
    color: var(--muted);
  }
</style>
