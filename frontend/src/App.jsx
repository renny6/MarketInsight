import React, { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { 
  TrendingUp, Trash2, Calendar, Play, Loader2, 
  CheckCircle, XCircle, History, BookOpen, Plus, 
  AlertTriangle, RefreshCw, Clock, X, ShieldAlert 
} from 'lucide-react'

// Constants
const TIMEZONES = [
  "UTC", "America/New_York", "America/Chicago", 
  "America/Denver", "America/Los_Angeles", "Europe/London", 
  "Europe/Paris", "Asia/Tokyo", "Asia/Kolkata"
]

export default function App() {
  // App state
  const [watchlist, setWatchlist] = useState([])
  const [newTicker, setNewTicker] = useState('')
  const [reports, setReports] = useState([])
  const [selectedReport, setSelectedReport] = useState(null)
  const [jobRuns, setJobRuns] = useState([])
  
  // UI states
  const [loadingWatchlist, setLoadingWatchlist] = useState(false)
  const [loadingReports, setLoadingReports] = useState(false)
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [submittingTicker, setSubmittingTicker] = useState(false)
  const [schedulerTicker, setSchedulerTicker] = useState(null) // Ticker being scheduled
  const [scheduleForm, setScheduleForm] = useState({ hour: 9, minute: 0, timezone: 'UTC' })
  const [actionMessage, setActionMessage] = useState(null) // Toast notification
  const [pollingActive, setPollingActive] = useState(false) // Trigger polling when item is processing

  // Show a temporary toast message
  const showToast = (message, type = 'success') => {
    setActionMessage({ text: message, type })
    setTimeout(() => setActionMessage(null), 4000)
  }

  // Fetch Watchlist
  const fetchWatchlist = async (silent = false) => {
    if (!silent) setLoadingWatchlist(true)
    try {
      const res = await fetch('/api/watchlist')
      if (!res.ok) throw new Error('Failed to fetch watchlist')
      const data = await res.json()
      setWatchlist(data)
      
      // If any ticker is processing, turn on polling
      const isAnyProcessing = data.some(item => item.is_processing)
      if (isAnyProcessing) {
        setPollingActive(true)
      } else if (pollingActive) {
        // If we were polling and now nothing is processing, refresh reports/jobs
        fetchReports(true)
        fetchJobRuns(true)
        setPollingActive(false)
      }
    } catch (err) {
      console.error(err)
      showToast('Error loading watchlist', 'error')
    } finally {
      if (!silent) setLoadingWatchlist(false)
    }
  }

  // Fetch Report List (Sidebar history)
  const fetchReports = async (silent = false) => {
    if (!silent) setLoadingReports(true)
    try {
      const res = await fetch('/api/reports')
      if (!res.ok) throw new Error('Failed to fetch reports')
      const data = await res.json()
      setReports(data)
    } catch (err) {
      console.error(err)
      showToast('Error loading report history', 'error')
    } finally {
      if (!silent) setLoadingReports(false)
    }
  }

  // Fetch Job Runs (Audit Log)
  const fetchJobRuns = async (silent = false) => {
    if (!silent) setLoadingJobs(true)
    try {
      const res = await fetch('/api/jobs')
      if (!res.ok) throw new Error('Failed to fetch jobs log')
      const data = await res.json()
      setJobRuns(data)
    } catch (err) {
      console.error(err)
      showToast('Error loading audit logs', 'error')
    } finally {
      if (!silent) setLoadingJobs(false)
    }
  }

  // Fetch Specific Report Details
  const viewReport = async (reportId) => {
    try {
      const res = await fetch(`/api/reports/id/${reportId}`)
      if (!res.ok) throw new Error('Failed to fetch report details')
      const data = await res.json()
      setSelectedReport(data)
    } catch (err) {
      console.error(err)
      showToast('Error retrieving report details', 'error')
    }
  }

  // Fetch latest report for a ticker
  const viewLatestReportForTicker = async (ticker) => {
    try {
      const res = await fetch(`/api/reports/${ticker}`)
      if (res.status === 404) {
        showToast(`No reports generated yet for ${ticker}. Trigger a manual analysis!`, 'warning')
        return
      }
      if (!res.ok) throw new Error('Failed to fetch latest report')
      const data = await res.json()
      setSelectedReport(data)
    } catch (err) {
      console.error(err)
      showToast(`Error retrieving latest report for ${ticker}`, 'error')
    }
  }

  // Add Ticker
  const addTicker = async (e) => {
    e.preventDefault()
    const ticker = newTicker.trim().toUpperCase()
    if (!ticker) return
    
    setSubmittingTicker(true)
    try {
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker })
      })
      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || 'Failed to add ticker')
      }

      if (data.status === 'already_exists') {
        showToast(`${ticker} is already in your watchlist!`, 'warning')
      } else {
        showToast(`Successfully added ${ticker} to watchlist!`)
        setNewTicker('')
        fetchWatchlist()
      }
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setSubmittingTicker(false)
    }
  }

  // Remove Ticker
  const deleteTicker = async (ticker) => {
    if (!confirm(`Are you sure you want to remove ${ticker} from your watchlist?`)) return
    try {
      const res = await fetch(`/api/watchlist/${ticker}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Failed to delete ticker')
      showToast(`Removed ${ticker} from watchlist`)
      fetchWatchlist()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // Trigger Report Manually
  const triggerReport = async (ticker) => {
    try {
      const res = await fetch(`/api/watchlist/trigger/${ticker}`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to trigger report')
      
      if (data.status === 'already_running') {
        showToast(data.message, 'warning')
      } else {
        showToast(`Analysis pipeline triggered for ${ticker} in the background!`)
        setPollingActive(true)
        fetchWatchlist(true)
      }
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // Save Schedule
  const saveSchedule = async (e) => {
    e.preventDefault()
    if (!schedulerTicker) return

    try {
      const res = await fetch('/api/watchlist/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: schedulerTicker,
          hour: parseInt(scheduleForm.hour),
          minute: parseInt(scheduleForm.minute),
          timezone: scheduleForm.timezone
        })
      })
      if (!res.ok) throw new Error('Failed to update schedule')
      const data = await res.json()
      
      showToast(`Scheduled ${schedulerTicker} successfully! UTC run: ${data.utc_time}`)
      setSchedulerTicker(null)
      fetchWatchlist()
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // Open Scheduler Modal/Form
  const openScheduler = (item) => {
    setSchedulerTicker(item.ticker)
    setScheduleForm({
      hour: item.cron_hour !== null ? item.cron_hour : 9,
      minute: item.cron_minute !== null ? item.cron_minute : 0,
      timezone: 'UTC'
    })
  }

  // Initial Load
  useEffect(() => {
    fetchWatchlist()
    fetchReports()
    fetchJobRuns()
  }, [])

  // Auto-polling when backend is generating reports
  useEffect(() => {
    let interval
    if (pollingActive) {
      interval = setInterval(() => {
        fetchWatchlist(true)
        fetchJobRuns(true)
      }, 5000) // Poll every 5 seconds
    }
    return () => clearInterval(interval)
  }, [pollingActive])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      
      {/* Toast Notification */}
      {actionMessage && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border ${
          actionMessage.type === 'error' ? 'bg-red-950/90 border-red-500/50 text-red-200' :
          actionMessage.type === 'warning' ? 'bg-amber-950/90 border-amber-500/50 text-amber-200' :
          'bg-slate-900/90 border-indigo-500/50 text-indigo-200'
        }`}>
          {actionMessage.type === 'error' ? <AlertTriangle className="h-5 w-5 text-red-400" /> :
           actionMessage.type === 'warning' ? <AlertTriangle className="h-5 w-5 text-amber-400" /> :
           <CheckCircle className="h-5 w-5 text-indigo-400" />}
          <span className="text-sm font-medium">{actionMessage.text}</span>
        </div>
      )}

      {/* Global Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-600/20 p-2 rounded-lg border border-indigo-500/30">
              <TrendingUp className="h-6 w-6 text-indigo-400" />
            </div>
            <div>
              <span className="font-display font-bold text-xl tracking-tight bg-gradient-to-r from-indigo-400 via-purple-400 to-indigo-300 bg-clip-text text-transparent">
                MarketInsight
              </span>
              <span className="text-xs block text-slate-500 font-medium">Autonomous Agentic Research</span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs font-semibold text-slate-400">
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/60 border border-slate-700/50">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
              FastAPI backend connected
            </span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* LEFT COLUMN: Controls & watchlist & logs */}
        <section className="lg:col-span-4 flex flex-col gap-8">
          
          {/* Watchlist card */}
          <div className="glass-effect rounded-2xl p-6 shadow-xl relative overflow-hidden">
            {/* Visual background gradient glow */}
            <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-2xl pointer-events-none"></div>
            
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display font-semibold text-lg flex items-center gap-2 text-slate-200">
                <span>Stock Watchlist</span>
                <span className="text-xs font-normal text-slate-400">({watchlist.length}/5 quota)</span>
              </h2>
              <button 
                onClick={() => fetchWatchlist()}
                className="text-slate-400 hover:text-indigo-400 transition-colors p-1"
                title="Refresh Watchlist"
              >
                <RefreshCw className={`h-4 w-4 ${loadingWatchlist ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {/* Add stock form */}
            <form onSubmit={addTicker} className="flex gap-2 mb-6">
              <input
                id="add-ticker-input"
                type="text"
                value={newTicker}
                onChange={(e) => setNewTicker(e.target.value)}
                placeholder="Enter stock ticker (e.g. NVDA)"
                className="flex-1 bg-slate-900 border border-slate-700/60 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-indigo-500 text-slate-100 placeholder-slate-500 transition-all font-sans"
              />
              <button
                type="submit"
                disabled={submittingTicker || watchlist.length >= 5}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 transition-colors px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-1.5 shadow-md shadow-indigo-600/10 cursor-pointer disabled:cursor-not-allowed"
              >
                {submittingTicker ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                <span>Add</span>
              </button>
            </form>

            {/* Watchlist list */}
            {loadingWatchlist && watchlist.length === 0 ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
              </div>
            ) : watchlist.length === 0 ? (
              <div className="text-center py-8 border border-dashed border-slate-800 rounded-xl">
                <p className="text-slate-500 text-sm">Your watchlist is empty.</p>
                <p className="text-slate-600 text-xs mt-1">Add a ticker above to get started.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {watchlist.map((item) => (
                  <div 
                    key={item.id} 
                    className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-xl flex items-center justify-between hover:border-slate-700/60 transition-all group"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-display font-bold text-slate-100">{item.ticker}</span>
                        {item.is_processing && (
                          <span className="flex items-center gap-1 text-[10px] bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full font-semibold animate-pulse">
                            <Loader2 className="h-2.5 w-2.5 animate-spin" />
                            Running
                          </span>
                        )}
                        {item.last_error && !item.is_processing && (
                          <span className="group-hover:block hidden text-[10px] bg-red-500/10 border border-red-500/20 text-red-400 px-2 py-0.5 rounded-full font-semibold" title={item.last_error}>
                            Failed last run
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-1">
                        <Clock className="h-3 w-3" />
                        {item.cron_hour !== null && item.cron_minute !== null ? (
                          <span>Daily at {item.cron_hour.toString().padStart(2, '0')}:{item.cron_minute.toString().padStart(2, '0')} UTC</span>
                        ) : (
                          <span className="italic">No schedule set</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => viewLatestReportForTicker(item.ticker)}
                        className="p-1.5 text-slate-400 hover:text-indigo-400 hover:bg-slate-800/50 rounded-lg transition-colors cursor-pointer"
                        title="View Report"
                      >
                        <BookOpen className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => openScheduler(item)}
                        className="p-1.5 text-slate-400 hover:text-amber-400 hover:bg-slate-800/50 rounded-lg transition-colors cursor-pointer"
                        title="Configure Schedule"
                      >
                        <Calendar className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => triggerReport(item.ticker)}
                        disabled={item.is_processing}
                        className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-slate-800/50 rounded-lg disabled:text-slate-700 transition-colors cursor-pointer disabled:cursor-not-allowed"
                        title="Trigger Analysis Now"
                      >
                        {item.is_processing ? <Loader2 className="h-4 w-4 animate-spin text-indigo-500" /> : <Play className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => deleteTicker(item.ticker)}
                        className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-slate-800/50 rounded-lg transition-colors cursor-pointer"
                        title="Remove Ticker"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Schedule Config Modal (inline widget form) */}
          {schedulerTicker && (
            <div className="glass-effect rounded-2xl p-6 shadow-xl border-l-4 border-amber-500 relative animate-in fade-in slide-in-from-top-4 duration-300">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display font-semibold text-base text-slate-200">
                  Configure Schedule: {schedulerTicker}
                </h3>
                <button onClick={() => setSchedulerTicker(null)} className="text-slate-400 hover:text-slate-200 cursor-pointer">
                  <X className="h-4 w-4" />
                </button>
              </div>

              <form onSubmit={saveSchedule} className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5 font-medium">Trigger Hour</label>
                    <input
                      type="number"
                      min="0"
                      max="23"
                      value={scheduleForm.hour}
                      onChange={(e) => setScheduleForm({...scheduleForm, hour: e.target.value})}
                      className="w-full bg-slate-900 border border-slate-700/60 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1.5 font-medium">Trigger Minute</label>
                    <input
                      type="number"
                      min="0"
                      max="59"
                      value={scheduleForm.minute}
                      onChange={(e) => setScheduleForm({...scheduleForm, minute: e.target.value})}
                      className="w-full bg-slate-900 border border-slate-700/60 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 text-slate-100"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-slate-400 mb-1.5 font-medium">User Local Timezone</label>
                  <select
                    value={scheduleForm.timezone}
                    onChange={(e) => setScheduleForm({...scheduleForm, timezone: e.target.value})}
                    className="w-full bg-slate-900 border border-slate-700/60 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 text-slate-100"
                  >
                    {TIMEZONES.map(tz => (
                      <option key={tz} value={tz}>{tz}</option>
                    ))}
                  </select>
                </div>

                <div className="flex gap-2 justify-end mt-2">
                  <button
                    type="button"
                    onClick={() => setSchedulerTicker(null)}
                    className="bg-slate-800 hover:bg-slate-700 transition-colors px-3 py-2 rounded-xl text-xs font-semibold cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="bg-amber-600 hover:bg-amber-500 transition-colors px-4 py-2 rounded-xl text-xs font-semibold shadow-md shadow-amber-600/10 cursor-pointer"
                  >
                    Save Schedule
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Sidebar Report History list */}
          <div className="glass-effect rounded-2xl p-6 shadow-xl flex-1 flex flex-col min-h-[300px]">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-lg flex items-center gap-2 text-slate-200">
                <History className="h-5 w-5 text-indigo-400" />
                <span>Reports Vault</span>
              </h2>
              <button 
                onClick={() => fetchReports()} 
                className="text-slate-400 hover:text-indigo-400 transition-colors"
                title="Refresh Report List"
              >
                <RefreshCw className={`h-4 w-4 ${loadingReports ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {loadingReports && reports.length === 0 ? (
              <div className="flex justify-center items-center flex-1">
                <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
              </div>
            ) : reports.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center border border-dashed border-slate-800 rounded-xl py-12">
                <BookOpen className="h-8 w-8 text-slate-600 mb-2" />
                <p className="text-slate-500 text-sm">No reports archived.</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto max-h-[350px] pr-1 flex flex-col gap-2">
                {reports.map((report) => (
                  <button
                    key={report.id}
                    onClick={() => viewReport(report.id)}
                    className={`w-full text-left p-3.5 rounded-xl border transition-all flex items-center justify-between cursor-pointer ${
                      selectedReport?.id === report.id
                        ? 'bg-indigo-600/10 border-indigo-500/50 text-indigo-200'
                        : 'bg-slate-900/40 border-slate-800/80 text-slate-300 hover:border-slate-700/60 hover:bg-slate-900/80'
                    }`}
                  >
                    <div>
                      <span className="font-display font-bold block">{report.ticker}</span>
                      <span className="text-[10px] text-slate-500 block mt-1">
                        {new Date(report.generated_at).toLocaleString()}
                      </span>
                    </div>
                    <BookOpen className={`h-4 w-4 ${selectedReport?.id === report.id ? 'text-indigo-400' : 'text-slate-500'}`} />
                  </button>
                ))}
              </div>
            )}
          </div>

        </section>

        {/* RIGHT COLUMN: Large Report display area */}
        <section className="lg:col-span-8 flex flex-col gap-8">
          
          {/* Main report card wrapper */}
          <div className="glass-effect rounded-2xl p-8 shadow-xl flex-1 flex flex-col relative overflow-hidden min-h-[500px]">
            {/* Visual background gradient glow */}
            <div className="absolute -top-12 -right-12 w-64 h-64 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none"></div>

            {selectedReport ? (
              <div className="flex-1 flex flex-col animate-in fade-in duration-300">
                
                {/* Header detail */}
                <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-6 mb-6">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="text-3xl font-display font-extrabold tracking-tight bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
                        {selectedReport.ticker}
                      </span>
                      <span className="text-xs bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-3 py-1 rounded-full font-semibold uppercase tracking-wider">
                        Financial Report
                      </span>
                    </div>
                    <span className="text-xs text-slate-400 block mt-1 flex items-center gap-1">
                      <Clock className="h-3 w-3 inline text-slate-500" />
                      Generated at: {new Date(selectedReport.generated_at).toLocaleString()}
                    </span>
                  </div>
                  
                  {/* Quantitative Quick Metrics badges */}
                  {selectedReport.quantitative_metrics && Object.keys(selectedReport.quantitative_metrics).length > 0 && (
                    <div className="flex gap-3 flex-wrap">
                      {Object.entries(selectedReport.quantitative_metrics).slice(0, 3).map(([key, val]) => (
                        <div key={key} className="bg-slate-900 border border-slate-800/80 px-3.5 py-1.5 rounded-xl text-center">
                          <span className="text-[10px] text-slate-500 block uppercase font-bold tracking-wider">{key}</span>
                          <span className="text-sm font-semibold text-slate-200">{String(val)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Markdown body rendering */}
                <div className="prose-report flex-1 overflow-y-auto pr-2 max-h-[700px]">
                  <ReactMarkdown>{selectedReport.markdown_content}</ReactMarkdown>
                </div>

              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center py-20">
                <div className="bg-indigo-950/40 p-4 rounded-full border border-indigo-500/20 mb-4 animate-bounce">
                  <TrendingUp className="h-10 w-10 text-indigo-400" />
                </div>
                <h3 className="font-display font-semibold text-xl text-slate-200">No Report Selected</h3>
                <p className="text-slate-500 text-sm max-w-sm mt-2">
                  Select a ticker from your watchlist to view its latest report, or choose an archived report from the Reports Vault.
                </p>
              </div>
            )}
          </div>

          {/* Job execution log section (Audit Log) */}
          <div className="glass-effect rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-lg flex items-center gap-2 text-slate-200">
                <ShieldAlert className="h-5 w-5 text-indigo-400" />
                <span>Job Audit Log</span>
              </h2>
              <button 
                onClick={() => fetchJobRuns()} 
                className="text-slate-400 hover:text-indigo-400 transition-colors"
                title="Refresh Logs"
              >
                <RefreshCw className={`h-4 w-4 ${loadingJobs ? 'animate-spin' : ''}`} />
              </button>
            </div>

            {loadingJobs && jobRuns.length === 0 ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
              </div>
            ) : jobRuns.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-6">No background runs logged yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                      <th className="py-2.5">Ticker</th>
                      <th className="py-2.5">Triggered At</th>
                      <th className="py-2.5">Duration</th>
                      <th className="py-2.5">Status</th>
                      <th className="py-2.5">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobRuns.map((run) => (
                      <tr key={run.id} className="border-b border-slate-900 hover:bg-slate-900/30 transition-colors">
                        <td className="py-2.5 font-bold text-slate-200">{run.ticker}</td>
                        <td className="py-2.5 text-slate-400">
                          {new Date(run.triggered_at).toLocaleString()}
                        </td>
                        <td className="py-2.5 text-slate-400">
                          {run.execution_time_ms ? `${(run.execution_time_ms / 1000).toFixed(1)}s` : 'N/A'}
                        </td>
                        <td className="py-2.5">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${
                            run.status === 'SUCCESS'
                              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                              : 'bg-red-500/10 border-red-500/20 text-red-400'
                          }`}>
                            {run.status === 'SUCCESS' ? (
                              <>
                                <CheckCircle className="h-3 w-3" />
                                Success
                              </>
                            ) : (
                              <>
                                <XCircle className="h-3 w-3" />
                                Failed
                              </>
                            )}
                          </span>
                        </td>
                        <td className="py-2.5 text-slate-500 max-w-[200px] truncate" title={run.error_log}>
                          {run.error_log || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

        </section>

      </main>

      {/* Global Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-6 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-xs text-slate-600 font-medium">
          MarketInsight Dashboard © 2026. Made with React, Vite, and Tailwind CSS.
        </div>
      </footer>

    </div>
  )
}
