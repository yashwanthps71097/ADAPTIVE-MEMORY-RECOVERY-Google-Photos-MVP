import React, { useState, useEffect } from 'react';
import { 
  Search, Sparkles, MapPin, Users, Coffee, Plane, 
  ChevronRight, ArrowRight, CheckCircle2, Image as ImageIcon,
  HelpCircle, Home, LayoutGrid, Clock, Camera
} from 'lucide-react';

// Mock Data for the prototype
const MOCK_WEAK_RESULTS = [
  { id: 1, url: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=400&q=80', label: 'Beach' },
  { id: 2, url: 'https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=400&q=80', label: 'Cafe Exterior' },
  { id: 3, url: 'https://images.unsplash.com/photo-1529333166437-7750a6dd5a70?auto=format&fit=crop&w=400&q=80', label: 'Friends' },
  { id: 4, url: 'https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=400&q=80', label: 'Street' },
  { id: 5, url: 'https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?auto=format&fit=crop&w=400&q=80', label: 'Food' },
  { id: 6, url: 'https://images.unsplash.com/photo-1601225565147-3860bb63ecbc?auto=format&fit=crop&w=400&q=80', label: 'Sunset' },
];

const TARGET_PHOTO = 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=800&q=80'; // Cozy restaurant with friends

export default function AdaptiveMemoryRecoveryApp() {
  const [step, setStep] = useState(1);
  const [isAnalyzing, setIsAnalyzing] = useState(true);

  // Handle fake analysis delay for Step 2
  useEffect(() => {
    if (step === 2) {
      setIsAnalyzing(true);
      const timer = setTimeout(() => setIsAnalyzing(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [step]);

  // Handle fake processing delay for Step 6 (Path Updated)
  useEffect(() => {
    if (step === 6) {
      const timer = setTimeout(() => setStep(7), 2500);
      return () => clearTimeout(timer);
    }
  }, [step]);

  const resetApp = () => {
    setStep(1);
  };

  const Header = () => (
    <header className="border-b border-slate-200 bg-white sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2 text-slate-900 font-semibold text-lg">
          <Sparkles className="w-5 h-5 text-blue-600" />
          Adaptive Memory Recovery
        </div>
        <nav className="flex items-center gap-6 text-sm font-medium text-slate-500">
          <span className="hover:text-slate-900 cursor-pointer transition-colors text-blue-600">Memories</span>
          <span className="hover:text-slate-900 cursor-pointer transition-colors">Search</span>
          <span className="hover:text-slate-900 cursor-pointer transition-colors">Insights</span>
        </nav>
      </div>
    </header>
  );

  const FadeIn = ({ children, className = "" }) => (
    <div className={`animate-in fade-in duration-700 slide-in-from-bottom-4 ${className}`}>
      {children}
    </div>
  );

  const MemoryChip = ({ icon: Icon, label, isActive = false }) => (
    <div className={`flex items-center gap-2 px-4 py-2 rounded-full border ${isActive ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-slate-200 text-slate-700'} shadow-sm text-sm font-medium transition-all`}>
      {Icon && <Icon className="w-4 h-4" />}
      {label}
    </div>
  );

  const renderStep1 = () => (
    <FadeIn className="max-w-2xl mx-auto mt-24 text-center">
      <h1 className="text-4xl font-bold text-slate-900 tracking-tight mb-4">Find a photo you remember</h1>
      <p className="text-lg text-slate-500 mb-10">Describe the moment the way you remember it. You don't need the exact date, location, or keywords.</p>
      
      <div className="relative group">
        <div className="absolute inset-0 bg-blue-600 rounded-2xl blur opacity-20 group-hover:opacity-30 transition-opacity duration-500"></div>
        <div className="relative bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden flex items-center p-2 pl-6">
          <Search className="w-6 h-6 text-slate-400" />
          <input 
            type="text" 
            readOnly
            value="That small café we went to during our Goa trip with my friend."
            className="w-full bg-transparent border-none text-slate-900 text-lg px-4 py-4 focus:outline-none"
          />
          <button 
            onClick={() => setStep(2)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 rounded-xl font-medium transition-colors whitespace-nowrap"
          >
            Find my photo
          </button>
        </div>
      </div>

      <div className="mt-12 text-left">
        <p className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4 pl-2">Try a memory</p>
        <div className="grid grid-cols-2 gap-3">
          {["That Goa trip with my college friends", "The screenshot of the dress I wanted to buy", "The medicine photo I took last year", "That birthday dinner with my family"].map((text, i) => (
            <div key={i} className="bg-white border border-slate-100 rounded-xl p-4 text-sm text-slate-600 hover:border-blue-200 hover:shadow-md cursor-pointer transition-all flex items-center gap-3">
              <Clock className="w-4 h-4 text-slate-300" />
              {text}
            </div>
          ))}
        </div>
      </div>
    </FadeIn>
  );

  const renderStep2 = () => (
    <FadeIn className="max-w-2xl mx-auto mt-24">
      {isAnalyzing ? (
        <div className="flex flex-col items-center justify-center py-20 text-slate-500">
          <div className="relative w-16 h-16 mb-6">
            <div className="absolute inset-0 border-4 border-blue-100 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
            <Sparkles className="absolute inset-0 m-auto w-6 h-6 text-blue-600 animate-pulse" />
          </div>
          <p className="text-lg font-medium">Understanding your memory...</p>
        </div>
      ) : (
        <FadeIn className="bg-white rounded-3xl p-8 border border-slate-200 shadow-xl">
          <h2 className="text-2xl font-semibold text-slate-900 mb-6 flex items-center gap-2">
            <CheckCircle2 className="w-6 h-6 text-green-500" />
            I understood your memory as:
          </h2>
          
          <div className="flex flex-wrap gap-3 mb-8">
            <MemoryChip icon={MapPin} label="Goa" isActive />
            <MemoryChip icon={Users} label="Friend" isActive />
            <MemoryChip icon={Coffee} label="Café" isActive />
            <MemoryChip icon={Plane} label="Trip" isActive />
          </div>

          <div className="bg-slate-50 rounded-2xl p-6 mb-8 text-sm text-slate-600">
            <div className="flex gap-2 items-start">
              <Sparkles className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
              <p>You don't need to remember everything. We'll start with the clues you already have, and you can guide the search if needed.</p>
            </div>
          </div>

          <button 
            onClick={() => setStep(3)}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white px-6 py-4 rounded-xl font-medium transition-colors flex items-center justify-center gap-2 text-lg"
          >
            Search these memories <ArrowRight className="w-5 h-5" />
          </button>
        </FadeIn>
      )}
    </FadeIn>
  );

  const renderStep3 = () => (
    <FadeIn className="max-w-5xl mx-auto mt-12 pb-32">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-slate-900">Possible matches</h2>
          <p className="text-slate-500 mt-2">We found photos related to your memory, but the exact moment isn't clear yet.</p>
        </div>
        <div className="flex gap-2">
          <MemoryChip label="Goa" />
          <MemoryChip label="Friend" />
          <MemoryChip label="Café" />
          <MemoryChip label="Trip" />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6 mb-12">
        {MOCK_WEAK_RESULTS.map((photo) => (
          <div key={photo.id} className="relative aspect-square rounded-2xl overflow-hidden bg-slate-100 group">
            <img src={photo.url} alt={photo.label} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
          </div>
        ))}
      </div>

      {/* Confidence Banner */}
      <div className="fixed bottom-8 left-1/2 -translate-x-1/2 w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 flex flex-col sm:flex-row items-center justify-between gap-4 animate-in slide-in-from-bottom-10">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-amber-500"></div>
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Search Confidence: Low</span>
          </div>
          <p className="text-slate-900 font-medium">Not seeing the moment you're looking for?</p>
        </div>
        <button 
          onClick={() => setStep(4)}
          className="bg-slate-900 hover:bg-slate-800 text-white px-6 py-3 rounded-xl font-medium transition-colors shrink-0 whitespace-nowrap"
        >
          Help me find it
        </button>
      </div>
    </FadeIn>
  );

  const renderStep4 = () => (
    <FadeIn className="max-w-2xl mx-auto mt-24">
      <div className="bg-white rounded-3xl p-10 border border-slate-200 shadow-xl text-center">
        <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-6 text-blue-600">
          <HelpCircle className="w-8 h-8" />
        </div>
        <h2 className="text-3xl font-bold text-slate-900 mb-3">Let's narrow down the memory</h2>
        <p className="text-slate-500 mb-10 text-lg">One more detail may help narrow the moment. Do you remember what kind of place it was?</p>
        
        <div className="grid grid-cols-2 gap-4 text-left">
          {['Restaurant / Café', 'Beachside', 'Hotel / Resort', 'Street / Market'].map((opt) => (
            <button key={opt} className="p-4 border border-slate-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-all font-medium text-slate-700 flex items-center justify-between group">
              {opt}
              <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-blue-500" />
            </button>
          ))}
          <button 
            onClick={() => setStep(5)}
            className="col-span-2 p-4 mt-2 bg-slate-50 border border-slate-200 rounded-xl hover:bg-slate-100 hover:border-slate-300 transition-all font-medium text-slate-700 flex items-center justify-center gap-2 group ring-2 ring-transparent focus:ring-blue-500 relative overflow-hidden"
          >
            <span className="relative z-10">Not sure</span>
            <div className="absolute inset-0 bg-blue-100 opacity-0 group-hover:opacity-20 transition-opacity"></div>
          </button>
        </div>
      </div>
    </FadeIn>
  );

  const renderStep5 = () => (
    <FadeIn className="max-w-4xl mx-auto mt-16 text-center">
      <h2 className="text-4xl font-bold text-slate-900 mb-4">Which feels familiar?</h2>
      <p className="text-xl text-slate-500 mb-12 max-w-2xl mx-auto">
        You don't have to remember the answer. Choose anything that feels connected to the moment.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-left">
        {[
          { label: 'Restaurant', icon: Coffee, color: 'text-amber-600', bg: 'bg-amber-50', img: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=200&q=80' },
          { label: 'Beach', icon: MapPin, color: 'text-sky-600', bg: 'bg-sky-50', img: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=200&q=80' },
          { label: 'Travel', icon: Plane, color: 'text-emerald-600', bg: 'bg-emerald-50', img: 'https://images.unsplash.com/photo-1436491865332-7a61a109cc05?auto=format&fit=crop&w=200&q=80' },
          { label: 'Evening', icon: Clock, color: 'text-indigo-600', bg: 'bg-indigo-50', img: 'https://images.unsplash.com/photo-1517502884422-41eaead166d4?auto=format&fit=crop&w=200&q=80' },
        ].map((card) => (
          <button 
            key={card.label}
            onClick={() => card.label === 'Restaurant' ? setStep(6) : null}
            className="group relative flex flex-col h-64 rounded-2xl overflow-hidden border border-slate-200 hover:border-blue-500 hover:shadow-xl transition-all duration-300 text-left bg-white"
          >
            <div className="absolute inset-0 bg-black/20 group-hover:bg-black/10 transition-colors z-10"></div>
            <img src={card.img} alt={card.label} className="absolute inset-0 w-full h-full object-cover group-hover:scale-110 transition-transform duration-700" />
            <div className="absolute bottom-0 left-0 right-0 p-5 bg-gradient-to-t from-black/80 to-transparent z-20">
              <div className={`w-8 h-8 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center mb-3 text-white`}>
                <card.icon className="w-4 h-4" />
              </div>
              <span className="text-xl font-bold text-white">{card.label}</span>
            </div>
            {/* Outline the correct choice for demo purposes */}
            {card.label === 'Restaurant' && (
              <div className="absolute top-4 right-4 z-20">
                <span className="flex h-3 w-3 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-white"></span>
                </span>
              </div>
            )}
          </button>
        ))}
      </div>
      
      <button className="mt-12 text-slate-400 hover:text-slate-600 font-medium transition-colors">
        None of these feel familiar
      </button>
    </FadeIn>
  );

  const renderStep6 = () => (
    <FadeIn className="max-w-3xl mx-auto mt-24 text-center">
      <div className="relative w-20 h-20 mx-auto mb-8">
        <div className="absolute inset-0 border-4 border-blue-100 rounded-full"></div>
        <div className="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
        <Sparkles className="absolute inset-0 m-auto w-8 h-8 text-blue-600 animate-pulse" />
      </div>
      
      <h2 className="text-3xl font-bold text-slate-900 mb-12">Updating your memory path</h2>
      
      <div className="bg-white rounded-3xl p-10 border border-slate-200 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-400 to-indigo-500"></div>
        
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-400 uppercase tracking-wider w-32 text-right pr-6 border-r border-slate-200">Original</span>
            <div className="flex gap-2 flex-1 pl-6">
              <MemoryChip label="Goa" />
              <MemoryChip label="Friend" />
              <MemoryChip label="Café" />
              <MemoryChip label="Trip" />
            </div>
          </div>
          
          <div className="flex items-center justify-between opacity-0 animate-[fade-in_0.5s_ease-out_0.5s_forwards]">
            <span className="text-sm font-bold text-blue-500 uppercase tracking-wider w-32 text-right pr-6 border-r border-blue-200">Recognized</span>
            <div className="flex gap-2 flex-1 pl-6">
              <MemoryChip label="Restaurant" isActive />
            </div>
          </div>

          <div className="h-px bg-slate-100 my-2"></div>

          <div className="flex items-center justify-between opacity-0 animate-[fade-in_0.5s_ease-out_1s_forwards]">
            <span className="text-sm font-bold text-slate-900 uppercase tracking-wider w-32 text-right pr-6 border-r border-slate-200">New Path</span>
            <div className="flex gap-2 flex-1 pl-6 flex-wrap">
              <MemoryChip label="Goa" isActive />
              <MemoryChip label="Friend" isActive />
              <MemoryChip label="Café" isActive />
              <MemoryChip label="Restaurant" isActive />
              <MemoryChip label="Trip" isActive />
            </div>
          </div>
        </div>
      </div>
      
      <p className="mt-8 text-slate-500 font-medium animate-pulse">Searching collection with new context...</p>
    </FadeIn>
  );

  const renderStep7 = () => (
    <FadeIn className="max-w-6xl mx-auto mt-12 pb-20">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-slate-900">I think we found the moment</h2>
          <p className="text-slate-500 mt-2">These photos match more of the context you remembered.</p>
        </div>
        <div className="flex gap-2 flex-wrap max-w-md justify-end">
          <MemoryChip label="Goa" isActive />
          <MemoryChip label="Friend" isActive />
          <MemoryChip label="Restaurant" isActive />
          <MemoryChip label="Trip" isActive />
        </div>
      </div>

      <div className="grid grid-cols-4 gap-6">
        {/* Prominent Target Photo */}
        <div 
          onClick={() => setStep(8)}
          className="col-span-2 row-span-2 relative rounded-3xl overflow-hidden bg-slate-100 group cursor-pointer border-4 border-white shadow-2xl hover:shadow-blue-200 transition-all duration-300"
        >
          <img src={TARGET_PHOTO} alt="Target" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
          <div className="absolute top-6 left-6 bg-green-500/90 backdrop-blur-sm text-white px-4 py-2 rounded-full text-sm font-bold flex items-center gap-2 shadow-lg">
            <CheckCircle2 className="w-4 h-4" /> Strong context match
          </div>
          <div className="absolute inset-0 rounded-3xl ring-4 ring-inset ring-blue-500 opacity-0 group-hover:opacity-100 transition-opacity"></div>
        </div>

        {/* Filler weak results reshuffled slightly */}
        <div className="relative aspect-square rounded-2xl overflow-hidden bg-slate-100 group opacity-70 hover:opacity-100 transition-opacity">
          <img src={MOCK_WEAK_RESULTS[2].url} alt="Filler" className="w-full h-full object-cover" />
        </div>
        <div className="relative aspect-square rounded-2xl overflow-hidden bg-slate-100 group opacity-70 hover:opacity-100 transition-opacity">
          <img src={MOCK_WEAK_RESULTS[4].url} alt="Filler" className="w-full h-full object-cover" />
        </div>
        <div className="relative aspect-square rounded-2xl overflow-hidden bg-slate-100 group opacity-70 hover:opacity-100 transition-opacity">
          <img src={MOCK_WEAK_RESULTS[1].url} alt="Filler" className="w-full h-full object-cover" />
        </div>
        <div className="relative aspect-square rounded-2xl overflow-hidden bg-slate-100 group opacity-70 hover:opacity-100 transition-opacity">
          <img src={MOCK_WEAK_RESULTS[0].url} alt="Filler" className="w-full h-full object-cover" />
        </div>
      </div>
    </FadeIn>
  );

  const renderStep8 = () => (
    <FadeIn className="fixed inset-0 z-50 bg-slate-900/95 backdrop-blur-md flex items-center justify-center p-6 overflow-y-auto">
      <div className="w-full max-w-5xl bg-white rounded-3xl shadow-2xl overflow-hidden flex flex-col md:flex-row my-auto animate-in zoom-in-95 duration-500">
        <div className="md:w-3/5 bg-black relative">
          <img src={TARGET_PHOTO} alt="Found Photo" className="w-full h-full object-cover opacity-90" />
          <div className="absolute bottom-6 left-6 right-6 flex justify-between items-end text-white drop-shadow-md">
            <div>
              <p className="text-lg font-medium">October 24, 2023</p>
              <p className="text-white/80 flex items-center gap-1"><MapPin className="w-4 h-4" /> Anjuna, Goa</p>
            </div>
            <div className="bg-black/40 backdrop-blur-md rounded-full px-4 py-2 flex items-center gap-2 text-sm border border-white/20">
              <Camera className="w-4 h-4" /> Pixel 8 Pro
            </div>
          </div>
        </div>
        
        <div className="md:w-2/5 p-10 flex flex-col">
          <div className="flex items-center gap-3 text-green-600 mb-2">
            <span className="text-4xl">🎉</span>
            <h2 className="text-3xl font-bold text-slate-900">Found it</h2>
          </div>
          <p className="text-slate-500 mb-10 text-lg">This photo matches the clues you remembered and recognized.</p>
          
          <div className="mb-8 flex-1">
            <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4">Final Retrieval Path</h3>
            <div className="flex flex-col gap-2 relative">
              <div className="absolute left-4 top-4 bottom-4 w-px bg-blue-100"></div>
              {['Goa', 'Friend', 'Trip', 'Café', 'Restaurant (Recognized)'].map((step, i) => (
                <div key={i} className="flex items-center gap-4 relative z-10">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${i === 4 ? 'bg-blue-600 text-white' : 'bg-blue-50 text-blue-600 border border-blue-200'}`}>
                    {i + 1}
                  </div>
                  <span className={`font-medium ${i === 4 ? 'text-slate-900' : 'text-slate-600'}`}>{step}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-slate-50 rounded-2xl p-6 mb-8 border border-slate-100">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Session Analytics</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-2xl font-bold text-slate-900">2</p>
                <p className="text-xs text-slate-500">Search attempts</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">2</p>
                <p className="text-xs text-slate-500">Recovery steps</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">1</p>
                <p className="text-xs text-slate-500">Recognized clues</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-green-600">100%</p>
                <p className="text-xs text-slate-500">Success rate</p>
              </div>
            </div>
          </div>
          
          <div className="flex gap-3">
            <button 
              onClick={resetApp}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-6 py-4 rounded-xl font-medium transition-colors"
            >
              Done
            </button>
            <button 
              onClick={resetApp}
              className="flex-1 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 px-6 py-4 rounded-xl font-medium transition-colors"
            >
              Find another
            </button>
          </div>
        </div>
      </div>
    </FadeIn>
  );

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900 selection:bg-blue-200">
      <Header />
      <main className="px-6">
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
        {step === 4 && renderStep4()}
        {step === 5 && renderStep5()}
        {step === 6 && renderStep6()}
        {step === 7 && renderStep7()}
        {step === 8 && renderStep8()}
      </main>
    </div>
  );
}