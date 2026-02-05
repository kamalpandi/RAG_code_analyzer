---
# Project: Support Ticket Management System

## High-Level Architectural Summary

#### Project Overview:
The project is designed to manage customer support requests efficiently using various strategies for ticket processing. It includes components that handle ticket creation, storage, and processing.

#### Key Components:

1. **SupportTicket Class:**
   - **Purpose:** Represents a single support ticket with attributes such as `id`, `customer`, and `issue`.
   - **Responsibilities:**
     - Stores the unique identifier for each ticket.
     - Holds information about the customer who created the ticket.
     - Contains details of the issue or problem reported.

2. **CustomerSupport Class:**
   - **Purpose:** Manages a collection of support tickets and provides methods to create new tickets and process them using different strategies.
   - **Responsibilities:**
     - Stores all created support tickets in a list.
     - Allows users to add new tickets with customer details and issue descriptions.
     - Provides methods to process tickets using various ordering strategies, such as FIFO (First In First Out), FILO (Last In First Out), random ordering, or blackhole ordering.

3. **Strategy Pattern:**
   - **Purpose:** Allows for dynamic selection of algorithms or behaviors at runtime, enabling flexibility in how support tickets are processed.
   - **Components:**
     - **Ordering Functions:** `fifo_ordering`, `filo_ordering`, `random_ordering`, and `blackhole_ordering`.
     - **Strategy Interface:** A callable that takes a list of `SupportTicket` objects and returns an ordered list.

4. **Main Application Logic:**
   - **Purpose:** Initializes the application, creates support tickets, processes them using different strategies, and prints details about each ticket.
   - **Components:**
     - **Initialization:** Sets up the `CustomerSupport` instance with an empty list of tickets.
     - **Ticket Creation:** Allows users to input customer details and issue descriptions to create new tickets.
     - **Processing Tickets:** Uses the `process_tickets` method with different ordering strategies to process all tickets.

#### Project Structure:
- **Files:**
  - `strategy-after-fn.py`: Contains the implementation of the strategy pattern using functions for ticket processing.
  - `strategy-before.py`: Demonstrates a simple implementation of the Strategy pattern in Python.
  - `strategy-before-fn.py`: Further refines the strategy pattern by using functions to handle different ordering strategies.
  - `support_ticket.py`: Defines the `SupportTicket` class.
  - `customer_support.py`: Implements the `CustomerSupport` class and handles ticket creation and processing.

#### Project Flow:
1. **Initialization:**
   - The application initializes with an empty list of support tickets.
2. **User Interaction:**
   - Users can input customer details and issue descriptions to create new support tickets.
3. **Processing Tickets:**
   - The user selects a processing strategy (e.g., FIFO, FILO, random).
   - The `CustomerSupport` class processes the tickets using the selected strategy.
4. **Output:**
   - Each processed ticket is printed with details for further review or action.

#### Project Considerations:
- **Scalability:** The project is designed to handle a large number of support tickets efficiently by storing them in a list and processing them using different strategies.
- **Maintainability:** By using the strategy pattern, the application can easily extend its functionality to include new ordering strategies without modifying the core logic.
- **Flexibility:** Users can choose from various processing strategies based on their needs or preferences.

This architecture ensures that the project is modular, scalable, and maintainable, making it suitable for managing customer support requests effectively.
---