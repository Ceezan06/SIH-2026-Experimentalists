import re
from transformers import pipeline

class MPLADSComplianceAuditor:
    def __init__(self):
        # Initialize Zero-Shot NLP Classifier for semantic policy auditing
        self.classifier = pipeline(
            "zero-shot-classification", 
            model="typeform/distilbert-base-uncased-mnli",
            device="cuda"  # Use GPU if available, else CPU
        )
        
        # Candidate labels derived directly from Section 5.2 Non-Permissible Works
        self.banned_labels = [
            "religious structure or place of worship",
            "welcome gate or swagat dwar",
            "residential building or housing",
            "commercial or private establishment",
            "land acquisition or land compensation",
            "maintenance or repair or recurring expense",
            "unauthorized colony construction",
            "statue or memorial or naming asset after a person"
        ]

    def audit_project(self, description: str, amount: float, is_trust: bool = False, is_outside_constituency: bool = False):
        violations = []
        warnings = []
        clause_references = []

        # ----------------------------------------------------
        # DETERMINISTIC RULES (Chapter 3, 5 & 6)
        # ----------------------------------------------------
        
        # Rule 1: Section 5.1.9 - Repair & Renovation Ceiling
        if "repair" in description.lower() or "renovation" in description.lower():
            if amount > 5000000: # ₹50 Lakhs
                violations.append("Repair/renovation recommendation exceeds annual cap of ₹50 Lakhs.")
                clause_references.append("Section 5.1.9")

        # Rule 2: Section 3.1.2.1 - Outside Constituency Ceiling
        if is_outside_constituency and amount > 2500000: # ₹25 Lakhs
            violations.append("Recommendations outside election region exceed annual ceiling of ₹25 Lakhs.")
            clause_references.append("Section 3.1.2.1")

        # Rule 3: Section 6.2.6.2 - Registered Societies & Trusts Ceiling
        if is_trust and amount > 5000000: # ₹50 Lakhs per year
            violations.append("Allocation to Registered Society/Trust exceeds annual limit of ₹50 Lakhs.")
            clause_references.append("Section 6.2.6.2")

        # Rule 4: Section 5.2.12 - Swagat Dwars / Welcome Gates Keyword Match
        if re.search(r'\b(swagat dwar|welcome gate|gate)\b', description, re.IGNORECASE):
            violations.append("Construction of Swagat Dwars or Welcome Gates is strictly prohibited.")
            clause_references.append("Section 5.2.12")

        # Rule 5: Section 5.2.4 - Naming of Assets
        if re.search(r'\b(named after|in memory of|statue of|memorial)\b', description, re.IGNORECASE):
            violations.append("Naming of assets or constructing statues/memorials after any person is prohibited.")
            clause_references.append("Section 5.2.4")

        # ----------------------------------------------------
        # NLP ZERO-SHOT SEMANTIC RULES (Section 5.2)
        # ----------------------------------------------------
        result = self.classifier(description, self.banned_labels)
        top_label = result['labels'][0]
        confidence = result['scores'][0]

        if confidence > 0.60: # 60% confidence threshold
            if top_label == "religious structure or place of worship":
                violations.append("Works of religious nature or within premises of religious worship are prohibited.")
                clause_references.append("Section 5.2.11")
                
            elif top_label == "residential building or housing":
                violations.append("Construction of residential buildings is prohibited.")
                clause_references.append("Section 5.2.2")
                
            elif top_label == "commercial or private establishment":
                violations.append("Works involving commercial and private establishments are non-permissible.")
                clause_references.append("Section 5.2.3")
                
            elif top_label == "land acquisition or land compensation":
                violations.append("Acquisition of land or land compensation payments are prohibited.")
                clause_references.append("Section 5.2.7")
                
            elif top_label == "unauthorized colony construction":
                violations.append("Works in unauthorized colonies are non-permissible.")
                clause_references.append("Section 5.2.13")

        # Determine Final Compliance Status
        is_compliant = len(violations) == 0
        
        return {
            "is_compliant": is_compliant,
            "violations": violations,
            "warnings": warnings,
            "clauses": list(set(clause_references)),
            "detected_category": top_label,
            "category_confidence": round(confidence * 100, 2)
        }