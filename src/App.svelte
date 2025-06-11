<script>
  import { onMount } from 'svelte';
  import Map from './components/Map.svelte';
  import Timeseries from './components/Timeseries.svelte';
  import Hotlist from './components/Hotlist.svelte';

  let allEvents = [];
  let dailyAverageRiskData = []; // For Timeseries: array of {date: 'YYYY-MM-DD', avgRisk: X}
  let top10Events = [];

  onMount(async () => {
    try {
      const response = await fetch('/data/latest.json'); // Fetches from the static folder
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      allEvents = data;
      processEventData(data);
    } catch (error) {
      console.error("Failed to fetch or process event data:", error);
      allEvents = []; // Ensure it's an array even on error
    }
  });

  function processEventData(events) {
    if (!events || events.length === 0) {
        dailyAverageRiskData = [];
        top10Events = [];
        return;
    }

    // Calculate Top 10 Events by risk_score
    top10Events = [...events] // Create a new array to sort
      .sort((a, b) => b.risk_score - a.risk_score)
      .slice(0, 10);

    // Calculate Global Average Risk for the last 14 days
    const riskByDay = {}; // Store sum of risks and count for each day
    const today = new Date();
    const fourteenDaysAgo = new Date(today);
    fourteenDaysAgo.setDate(today.getDate() - 14);

    events.forEach(event => {
      const eventDate = new Date(event.timestamp);
      if (eventDate >= fourteenDaysAgo && eventDate <= today) {
        const dayStr = eventDate.toISOString().split('T')[0]; // YYYY-MM-DD
        if (!riskByDay[dayStr]) {
          riskByDay[dayStr] = { totalRisk: 0, count: 0 };
        }
        riskByDay[dayStr].totalRisk += event.risk_score;
        riskByDay[dayStr].count += 1;
      }
    });

    const calculatedDailyAverages = [];
    for (let i = 0; i < 14; i++) {
        const date = new Date(today);
        date.setDate(today.getDate() - i);
        const dayStr = date.toISOString().split('T')[0];

        if (riskByDay[dayStr] && riskByDay[dayStr].count > 0) {
            calculatedDailyAverages.push({
                date: dayStr,
                avgRisk: Math.round(riskByDay[dayStr].totalRisk / riskByDay[dayStr].count)
            });
        } else {
            // If no events for a day in the last 14 days, record 0 avg risk
             calculatedDailyAverages.push({ date: dayStr, avgRisk: 0 });
        }
    }
    // Data for chart should be in chronological order
    dailyAverageRiskData = calculatedDailyAverages.sort((a,b) => new Date(a.date) - new Date(b.date));
  }

</script>

<main>
  <header>
    <h1>Geopolitical Risk Dashboard</h1>
  </header>

  <div class="dashboard-layout">
    <div class="map-container">
      <Map events={allEvents} />
    </div>
    <aside class="sidebar">
      <div class="timeseries-container">
        <Timeseries dailyGlobalAverageRisk={dailyAverageRiskData} />
      </div>
      <div class="hotlist-container">
        <Hotlist events={top10Events} />
      </div>
    </aside>
  </div>

  <footer>
    <p>Data processed on: {new Date().toLocaleDateString()} {new Date().toLocaleTimeString()}</p>
  </footer>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
      Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
    background-color: #f4f7f9;
    color: #333;
  }

  main {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 100vh;
  }

  header {
    width: 100%;
    background-color: #2c3e50;
    color: white;
    padding: 1rem 0;
    text-align: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }

  header h1 {
    margin: 0;
    font-size: 1.8rem;
  }

  .dashboard-layout {
    display: flex;
    flex-wrap: wrap; /* Allow wrapping for smaller screens if necessary */
    padding: 20px;
    gap: 20px;
    width: 100%;
    max-width: 1600px; /* Max width for the dashboard content */
    box-sizing: border-box;
  }

  .map-container {
    flex: 3; /* Map takes more space */
    min-width: 300px; /* Minimum width for the map */
    background-color: #fff;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }

  .sidebar {
    flex: 1; /* Sidebar takes less space */
    display: flex;
    flex-direction: column;
    gap: 20px;
    min-width: 280px; /* Minimum width for sidebar elements */
  }

  .timeseries-container,
  .hotlist-container {
    background-color: #fff;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }

  footer {
    width: 100%;
    text-align: center;
    padding: 15px 0;
    font-size: 0.9em;
    color: #777;
    margin-top: auto; /* Pushes footer to the bottom */
  }

  /* Basic responsiveness: stack layout on smaller screens */
  @media (max-width: 768px) {
    .dashboard-layout {
      flex-direction: column;
    }
    .map-container, .sidebar {
      flex: 1 1 100%; /* Take full width when stacked */
    }
  }
</style>
