from typing import List, Optional

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None


class Experience(BaseModel):
    company: str = ""
    role: str = ""
    location: Optional[str] = None
    start_date: str = ""
    end_date: str = ""
    bullets: List[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: List[str] = Field(default_factory=list)
    bullets: List[str] = Field(default_factory=list)
    link: Optional[str] = None


class Skills(BaseModel):
    technical: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)


class Resume(BaseModel):
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    experience: List[Experience] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    skills: Skills = Field(default_factory=Skills)
    education: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)


class JobDescription(BaseModel):
    title: str = ""
    company: str = ""
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
