<script>
  export let events = []; // Expected: array of top 10 event objects
                          // Each event: { title: "...", source_url: "...", risk_score: X, ... }
</script>

<div class="hotlist-container">
  <h2>Top 10 Hotspots</h2>
  {#if events && events.length > 0}
    <ol class="hotlist">
      {#each events as event, i (event.source_url || event.title + i)}
        <li class="hotlist-item">
          <a href={event.source_url || '#'} target="_blank" rel="noopener noreferrer" title={event.title}>
            {i + 1}. {event.title || 'Event title not available'}
          </a>
          {#if event.risk_score != null}
            <span class="risk-score-badge" title="Risk Score: {event.risk_score}">
              {event.risk_score}
            </span>
          {/if}
        </li>
      {/each}
    </ol>
  {:else}
    <p class="no-hotspots-message">No current hotspots to display.</p>
  {/if}
</div>

<style>
  .hotlist-container {
    padding: 10px;
    /* background-color: #f9f9f9; */ /* Matches App.svelte's container styling */
    /* border-radius: 8px; */
    /* box-shadow: 0 1px 3px rgba(0,0,0,0.1); */
  }

  h2 {
    font-size: 1.4em;
    color: #333;
    margin-top: 0;
    margin-bottom: 15px;
    text-align: center;
  }

  .hotlist {
    list-style-type: none; /* Remove default numbering if using custom badges or numbers */
    padding-left: 0;
    margin: 0;
  }

  .hotlist-item {
    display: flex; /* Align link and badge */
    justify-content: space-between; /* Push badge to the right */
    align-items: center; /* Vertically align items */
    padding: 8px 5px;
    border-bottom: 1px solid #eee;
    font-size: 0.95em;
  }

  .hotlist-item:last-child {
    border-bottom: none;
  }

  .hotlist-item a {
    color: #007bff; /* Standard link blue */
    text-decoration: none;
    flex-grow: 1; /* Allow link to take available space */
    margin-right: 10px; /* Space before badge */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis; /* Add ellipsis for long titles */
  }

  .hotlist-item a:hover,
  .hotlist-item a:focus {
    text-decoration: underline;
    color: #0056b3;
  }

  .risk-score-badge {
    background-color: #e9ecef;
    color: #495057;
    padding: 3px 8px;
    border-radius: 10px;
    font-size: 0.8em;
    font-weight: bold;
    min-width: 20px; /* Ensure badge has some width even for single digit */
    text-align: center;
  }

  /* Optional: Color coding for risk score badges */
  /* These thresholds should ideally match those used in Map.svelte for consistency */
  .hotlist-item .risk-score-badge[title*="Risk Score: 7"], /* For scores 70-100 */
  .hotlist-item .risk-score-badge[title*="Risk Score: 8"],
  .hotlist-item .risk-score-badge[title*="Risk Score: 9"],
  .hotlist-item .risk-score-badge[title*="Risk Score: 100"] {
    background-color: #dc3545; /* Red */
    color: white;
  }

  .hotlist-item .risk-score-badge[title*="Risk Score: 4"], /* For scores 40-69 */
  .hotlist-item .risk-score-badge[title*="Risk Score: 5"],
  .hotlist-item .risk-score-badge[title*="Risk Score: 6"] {
    background-color: #ffc107; /* Orange/Yellow */
    color: #212529;
  }
  /* Add more rules for yellow/green if desired */


  .no-hotspots-message {
    text-align: center;
    color: #777;
    font-style: italic;
    padding: 20px 0;
  }
</style>
