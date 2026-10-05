import sets from '../pain-points.json' with {type:'json'};
import additions from '../persona-pains.json' with {type:'json'};

// Curated role families; source reference does not prove an attendee owns a pain.
export const personas=[
  {
    "id": "sales",
    "label": "Sales & prospecting",
    "description": "Sales teams, account executives and SDRs",
    "painIds": [
      "s1-04",
      "s1-02",
      "s1-08",
      "s1-09",
      "s1-10",
      "s1-03",
      "s1-06",
      "s1-11",
      "s1-12",
      "s1-13",
      "s2-01",
      "s2-03",
      "s2-04",
      "s2-07",
      "s2-08",
      "s2-09",
      "s2-10",
      "s2-11",
      "s2-12",
      "s2-13",
      "s3-01",
      "s3-02",
      "s3-08",
      "s3-10",
      "s4-11",
      "s4-07",
      "s4-09",
      "s4-10",
      "s4-12",
      "s4-13",
      "s1-22",
      "s3-22",
      "s4-21",
      "s4-22"
    ],
    "profiles": [
      1,
      3,
      4,
      5,
      6,
      7,
      8,
      9
    ]
  },
  {
    "id": "marketing",
    "label": "Marketing & growth",
    "description": "Demand generation, growth, ABM and field marketing",
    "painIds": [
      "s1-04",
      "s1-06",
      "s1-08",
      "s1-11",
      "s1-12",
      "s1-13",
      "s2-04",
      "s2-08",
      "s2-09",
      "s2-10",
      "s2-11",
      "s2-12",
      "s2-13",
      "s3-02",
      "s3-08",
      "s3-09",
      "s3-10",
      "s3-11",
      "s3-12",
      "s3-13",
      "s4-01",
      "s4-07",
      "s4-09",
      "s4-10",
      "s4-11",
      "s4-12",
      "s4-13",
      "s1-22",
      "s4-21",
      "s4-22"
    ],
    "profiles": [
      2,
      12,
      13,
      14,
      15
    ]
  },
  {
    "id": "customers",
    "label": "Customer success & accounts",
    "description": "Customer success, CS Ops, account management and renewals",
    "painIds": [
      "s1-15",
      "s1-16",
      "s1-20",
      "s1-17",
      "s1-14",
      "s1-18",
      "s1-19",
      "s2-14",
      "s2-15",
      "s2-16",
      "s2-17",
      "s2-18",
      "s2-19",
      "s2-20",
      "s3-14",
      "s3-15",
      "s3-16",
      "s3-17",
      "s3-18",
      "s3-19",
      "s3-20",
      "s4-14",
      "s4-15",
      "s4-16",
      "s4-17",
      "s4-18",
      "s4-19",
      "s4-20",
      "s4-04",
      "s3-01"
    ],
    "profiles": [
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25
    ]
  },
  {
    "id": "revops",
    "label": "Revenue & marketing ops",
    "description": "RevOps, sales ops, marketing ops, CRM data and reporting",
    "painIds": [
      "s1-01",
      "s1-05",
      "s4-24",
      "s4-06",
      "s1-07",
      "s1-02",
      "s1-17",
      "s1-18",
      "s1-20",
      "s2-02",
      "s2-06",
      "s2-15",
      "s2-17",
      "s2-25",
      "s3-01",
      "s3-03",
      "s3-05",
      "s3-06",
      "s3-07",
      "s3-19",
      "s4-01",
      "s4-03",
      "s4-04",
      "s4-08",
      "s4-25",
      "s4-12",
      "s4-16",
      "s4-20",
      "s1-23",
      "s3-23"
    ],
    "profiles": [
      16,
      26,
      27
    ]
  },
  {
    "id": "market",
    "label": "Strategy & market intelligence",
    "description": "Strategic BD, advisory, research and product marketing",
    "painIds": [
      "s1-21",
      "s1-22",
      "s2-21",
      "s2-22",
      "s3-21",
      "s3-22",
      "s4-21",
      "s4-22",
      "m-01",
      "m-02",
      "m-03",
      "m-04",
      "m-05",
      "m-06",
      "m-07",
      "m-08",
      "m-09",
      "m-10",
      "m-11",
      "m-12",
      "m-13",
      "m-14"
    ],
    "profiles": [
      17,
      31
    ]
  },
  {
    "id": "technology",
    "label": "Systems & AI",
    "description": "IT, GTM engineering, business systems and AI tools",
    "painIds": [
      "s1-23",
      "s3-23",
      "s2-23",
      "s1-25",
      "s4-25",
      "s1-24",
      "s2-24",
      "s2-25",
      "s3-24",
      "s3-25",
      "s4-23",
      "t-01",
      "t-02",
      "t-03",
      "t-04",
      "t-05",
      "t-06",
      "t-07",
      "t-08",
      "t-09",
      "t-10",
      "t-11",
      "t-12",
      "t-13",
      "t-14",
      "t-15",
      "t-16",
      "t-17",
      "t-18",
      "t-19"
    ],
    "profiles": [
      10,
      11,
      28,
      29,
      30,
      34
    ]
  },
  {
    "id": "support",
    "label": "Support & customer experience",
    "description": "Support, CX, service quality and ticket reviews",
    "painIds": [
      "u-01",
      "s2-20",
      "s4-18",
      "s4-19",
      "u-02",
      "u-03",
      "u-04",
      "u-05",
      "u-06",
      "u-07",
      "u-08",
      "u-09",
      "u-10",
      "u-11",
      "u-12",
      "u-13",
      "u-14",
      "u-15",
      "u-16",
      "u-17",
      "s2-17",
      "s1-20",
      "s2-19",
      "s4-17",
      "s2-25"
    ],
    "profiles": [
      32
    ]
  },
  {
    "id": "risk",
    "label": "Risk, fraud & payments",
    "description": "Case reviews, disputes, payments and compliance",
    "painIds": [
      "r-01",
      "r-02",
      "r-03",
      "r-04",
      "r-05",
      "r-06",
      "r-07",
      "r-08",
      "r-09",
      "r-10",
      "r-11",
      "r-12",
      "r-13",
      "r-14",
      "r-15",
      "r-16",
      "r-17",
      "r-18",
      "r-19",
      "r-20",
      "r-21",
      "r-22",
      "r-23",
      "r-24",
      "r-25"
    ],
    "profiles": [
      33
    ]
  }
];
// Roles offered at this GTM event. The full list stays for existing records and legacy code.
export const activePersonaIds=['sales','marketing','customers','revops','market','technology'];
export const activePersonas=personas.filter(p=>activePersonaIds.includes(p.id));
export function isActivePersona(id){return activePersonaIds.includes(id);}
export const roleMappingNotes={
  "sales": "W1 account selection and qualification; W2 for named-account engagement. Senior revenue leaders should choose the work they are discussing.",
  "marketing": "W2 by default; W1 when inbound matching, qualification or routing is the problem.",
  "customers": "W3, including CS Ops. CS Ops is not grouped with acquisition-focused RevOps.",
  "revops": "W1 by default; W2 or W3 where the actual workflow involves activation or post-sale handoffs.",
  "market": "W4. Strategic business development is distinct from SDR/BDR prospecting.",
  "technology": "Committee, implementation or builder context; no forced business wedge. General AI questions are cross-workflow.",
  "support": "W5 for triage, service QA and review; W3 only for explicit customer-risk or growth problems.",
  "risk": "W5 for case evidence and review decisions."
};
export const sharedAIIds=["s1-23","s1-24","s2-24","s3-25","s4-23","s4-25"];
export const painCatalog=[...sets.flat(),...additions];
const byId=new Map(painCatalog.map(p=>[p.id,p]));
export function getPersona(id){return personas.find(p=>p.id===id)||null;}
export function personaPains(id){
 const role=getPersona(id);if(!role)return [];
 const core=[...new Set(role.painIds)].filter(id=>!sharedAIIds.includes(id));
 const result=[];let ai=0;
 for(let i=0;i<core.length;i++){result.push(core[i]);if((i+1)%5===0&&ai<sharedAIIds.length)result.push(sharedAIIds[ai++]);}
 result.push(...sharedAIIds.slice(ai));return result.map(id=>byId.get(id)).filter(Boolean);
}
export function matchesPersona(id,painId){return Boolean(getPersona(id)&&(getPersona(id).painIds.includes(painId)||sharedAIIds.includes(painId)));}
